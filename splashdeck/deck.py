import fcntl, glob, io, os, select, time

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

vendorId, productId = 0x3142, 0x0060
width, height = 800, 480
packetSize = 1024


class DeckError(Exception):
    pass


def findDeck():
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            uevent = open(os.path.join(node, "device/uevent")).read()
        except OSError:
            continue
        if f"HID_ID=0003:{vendorId:08X}:{productId:08X}" not in uevent:
            continue
        rdesc = open(os.path.join(node, "device/report_descriptor"), "rb").read()
        if rdesc[:3] == b"\x06\xa0\xff":
            return "/dev/" + os.path.basename(node)
    return None


def fitImage(img, mode="fill", background="black"):
    img = ImageOps.exif_transpose(img).convert("RGB")
    if mode == "fill":
        return ImageOps.fit(img, (width, height), Image.LANCZOS)
    if mode == "stretch":
        return img.resize((width, height), Image.LANCZOS)
    if background == "blur":
        canvas = ImageOps.fit(img, (width // 8, height // 8), Image.BILINEAR).filter(ImageFilter.GaussianBlur(4)).resize((width, height), Image.BICUBIC)
        canvas = ImageEnhance.Brightness(canvas).enhance(0.6)
    else:
        canvas = Image.new("RGB", (width, height), (255, 255, 255) if background == "white" else (0, 0, 0))
    small = ImageOps.contain(img, (width, height), Image.LANCZOS)
    canvas.paste(small, ((width - small.width) // 2, (height - small.height) // 2))
    return canvas


def encode(img):
    buf = io.BytesIO()
    img.rotate(180).save(buf, "JPEG", quality=100, subsampling=2, optimize=False, progressive=False)
    return buf.getvalue()


def command(name, extra=b""):
    return b"CRT\x00\x00" + name + extra


def pad(data):
    return b"\x00" + data.ljust(packetSize, b"\x00")


def readAck(fd, timeout):
    r, _, _ = select.select([fd], [], [], timeout)
    if not r:
        return None
    return os.read(fd, 512)


def setBrightness(value, path=None):
    path = path or findDeck()
    if not path:
        raise DeckError("no deck")
    fd = os.open(path, os.O_RDWR)
    try:
        os.write(fd, pad(command(b"LIG", b"\x00\x00" + bytes([max(0, min(100, int(value)))]))))
    finally:
        os.close(fd)


def showLogo(fd):
    os.write(fd, pad(command(b"DIS")))
    os.write(fd, pad(command(b"CLE", b"\x00\x00DC")))
    time.sleep(0.5)
    os.write(fd, pad(command(b"DIS")))


def sendLogo(img, path=None, progress=None, show=True):
    path = path or findDeck()
    if not path:
        raise DeckError("no deck")
    jpeg = encode(img)
    try:
        fd = os.open(path, os.O_RDWR)
    except PermissionError:
        raise DeckError("no access")
    try:
        while readAck(fd, 0):
            pass
        os.write(fd, pad(command(b"LOG", len(jpeg).to_bytes(4, "big") + b"\x00")))
        time.sleep(3)
        chunks = [jpeg[i:i + packetSize] for i in range(0, len(jpeg), packetSize)]
        for i, chunk in enumerate(chunks):
            os.write(fd, pad(chunk))
            if progress:
                progress((i + 1) / len(chunks))
        ack = readAck(fd, 5)
        os.write(fd, pad(command(b"STP")))
        if not ack or not ack.startswith(b"ACK\x00\x00OK"):
            raise DeckError("no ack")
        if show:
            time.sleep(1)
            showLogo(fd)
    finally:
        os.close(fd)
    return len(jpeg)


def run(path, *commands):
    path = path or findDeck()
    if not path:
        raise DeckError("no deck")
    try:
        fd = os.open(path, os.O_RDWR)
    except PermissionError:
        raise DeckError("no access")
    try:
        for name, extra in commands:
            os.write(fd, pad(command(name, extra)))
    finally:
        os.close(fd)


def sleepScreen(path=None):
    run(path, (b"HAN", b""))


def wakeScreen(path=None):
    run(path, (b"DIS", b""))


def showLogoNow(path=None):
    path = path or findDeck()
    if not path:
        raise DeckError("no deck")
    fd = os.open(path, os.O_RDWR)
    try:
        showLogo(fd)
    finally:
        os.close(fd)


def firmware(path):
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        return None
    try:
        buf = bytearray(512)
        buf[0] = 1
        fcntl.ioctl(fd, (3 << 30) | (len(buf) << 16) | (ord("H") << 8) | 7, buf, True)
        return bytes(buf).split(b"\x00", 1)[0].decode("ascii", "replace") or None
    except OSError:
        return None
    finally:
        os.close(fd)


def deviceInfo(path=None):
    path = path or findDeck()
    if not path:
        return None
    usb = os.path.realpath(os.path.join("/sys/class/hidraw", os.path.basename(path), "device", "..", ".."))

    def attr(name):
        try:
            return open(os.path.join(usb, name)).read().strip()
        except OSError:
            return None

    return {
        "model": "D6 PRO",
        "path": path,
        "serial": attr("serial"),
        "firmware": firmware(path),
        "bus": attr("busnum"),
        "port": attr("devpath"),
        "speed": attr("speed"),
        "access": os.access(path, os.R_OK | os.W_OK),
        "usbId": f"{vendorId:04x}:{productId:04x}",
    }
