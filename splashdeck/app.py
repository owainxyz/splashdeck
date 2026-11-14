import base64, binascii, hashlib, io, json, os, re, shutil, stat, subprocess, sys, threading, time

from PIL import Image, ImageFile

from . import __version__, deck

modes = ["fill", "fit", "stretch"]
backgrounds = ["black", "white", "blur", "custom"]
webDir = os.path.join(os.path.dirname(__file__), "web")
dataHome = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
configHome = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
appData = os.path.join(dataHome, "splashdeck")
historyDir = os.path.join(appData, "history")
settingsPath = os.path.join(configHome, "splashdeck", "settings.json")
historyMax = 24
imageTypes = ("png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif")
maxFileBytes = 64 * 1024 * 1024
maxPixels = 64_000_000
maxUploadBytes = 16 * 1024 * 1024
historyName = re.compile(r"^\d{1,20}\.png$")
hexColour = re.compile(r"^#[0-9a-fA-F]{6}$")

Image.MAX_IMAGE_PIXELS = maxPixels
ImageFile.LOAD_TRUNCATED_IMAGES = False


class InputError(Exception):
    pass


def privateDir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def writePrivate(path, data):
    privateDir(os.path.dirname(path))
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def tightenStorage():
    for d in (appData, historyDir, os.path.dirname(settingsPath)):
        if os.path.isdir(d) and not os.path.islink(d):
            privateDir(d)
    for d, names in ((historyDir, os.listdir(historyDir) if os.path.isdir(historyDir) else []), (os.path.dirname(settingsPath), ["settings.json"])):
        for n in names:
            p = os.path.join(d, n)
            try:
                if stat.S_ISREG(os.lstat(p).st_mode):
                    os.chmod(p, 0o600)
            except OSError:
                pass


def dataUrl(data, mime):
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def decodePngUrl(url):
    prefix = "data:image/png;base64,"
    if not isinstance(url, str) or not url.startswith(prefix) or len(url) > maxUploadBytes * 4 // 3 + len(prefix) + 4:
        raise InputError("Bad image")
    try:
        data = base64.b64decode(url[len(prefix):], validate=True)
    except (binascii.Error, ValueError):
        raise InputError("Bad image")
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise InputError("Bad image")
    return data


def openImage(source, formats=None):
    try:
        img = Image.open(source, formats=formats)
        if img.width * img.height > maxPixels:
            raise InputError("Too large")
        img.load()
        return img
    except InputError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise InputError("Too large")
    except Exception:
        raise InputError("Can't open")


def imageToDataUrl(img, fmt="PNG", **kw):
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return dataUrl(buf.getvalue(), "image/" + fmt.lower())


def regularFile(path):
    try:
        st = os.stat(path)
    except (OSError, TypeError, ValueError):
        return False
    return stat.S_ISREG(st.st_mode) and st.st_size <= maxFileBytes


def currentWallpaper():
    for tool in ("awww", "swww"):
        exe = shutil.which(tool)
        if exe:
            try:
                out = subprocess.run([exe, "query"], capture_output=True, text=True, timeout=2, stdin=subprocess.DEVNULL).stdout
            except (OSError, subprocess.SubprocessError):
                out = ""
            m = re.search(r"image: (.+)$", out, re.M)
            if m and regularFile(m.group(1).strip()):
                return m.group(1).strip()
    state = os.path.expanduser("~/.local/state/wallpaper")
    if regularFile(state):
        path = open(state).read(4096).strip()
        if regularFile(path):
            return path
    exe = shutil.which("gsettings")
    if exe:
        for key in ("picture-uri-dark", "picture-uri"):
            try:
                out = subprocess.run([exe, "get", "org.gnome.desktop.background", key], capture_output=True, text=True, timeout=2, stdin=subprocess.DEVNULL).stdout.strip().strip("'")
            except (OSError, subprocess.SubprocessError):
                continue
            path = out.removeprefix("file://")
            if path and regularFile(path):
                return path
    return None


def loadSettings():
    try:
        with open(settingsPath) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    return cleanSettings(raw) if isinstance(raw, dict) else {}


def cleanSettings(values):
    out = {}
    if not isinstance(values, dict):
        return out
    if values.get("bg") in backgrounds:
        out["bg"] = values["bg"]
    if isinstance(values.get("color"), str) and hexColour.match(values["color"]):
        out["color"] = values["color"]
    if isinstance(values.get("keys"), bool):
        out["keys"] = values["keys"]
    b = values.get("brightness")
    if isinstance(b, (int, float)) and not isinstance(b, bool) and 0 <= b <= 100:
        out["brightness"] = int(b)
    t = values.get("lastSent")
    if isinstance(t, (int, float)) and not isinstance(t, bool) and 0 < t < 1e11:
        out["lastSent"] = float(t)
    return out


class Api:
    def __init__(self):
        self._window = None
        self._sendLock = threading.Lock()
        self._fileLock = threading.Lock()

    def state(self):
        return {"version": __version__, "device": deck.deviceInfo()}

    def settings(self):
        return loadSettings()

    def saveSettings(self, values):
        with self._fileLock:
            current = loadSettings()
            current.update(cleanSettings(values))
            writePrivate(settingsPath, json.dumps(current).encode())
        return True

    def wallpaper(self):
        path = currentWallpaper()
        return self._readImage(path) if path else None

    def pickImage(self):
        import webview
        start = os.path.expanduser("~/Pictures")
        result = self._window.create_file_dialog(webview.OPEN_DIALOG, directory=start if os.path.isdir(start) else "", file_types=("Images (" + ";".join("*." + t for t in imageTypes) + ")", "All files (*.*)"))
        if not result:
            return None
        return self._readImage(result[0])

    def exportImage(self, url):
        import webview
        try:
            data = decodePngUrl(url)
        except InputError as e:
            return {"error": str(e)}
        result = self._window.create_file_dialog(webview.SAVE_DIALOG, directory=os.path.expanduser("~"), save_filename="splash.png")
        if not result:
            return False
        path = result if isinstance(result, str) else result[0]
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return os.path.basename(path)

    def send(self, url):
        try:
            data = decodePngUrl(url)
        except InputError as e:
            return {"error": str(e)}
        if not self._sendLock.acquire(blocking=False):
            return {"error": "Busy"}
        threading.Thread(target=self._sendWorker, args=(data,), daemon=True).start()
        return {"started": True}

    def control(self, action, value=None):
        try:
            if action == "brightness":
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    return {"error": "Bad value"}
                level = max(0, min(100, int(value)))
                deck.setBrightness(level)
                self.saveSettings({"brightness": level})
            elif action == "sleep":
                deck.sleepScreen()
            elif action == "wake":
                deck.wakeScreen()
            elif action == "logo":
                deck.showLogoNow()
            else:
                return {"error": "Unknown"}
            return {"ok": True}
        except (deck.DeckError, OSError) as e:
            return {"error": str(e)}

    def history(self):
        items = []
        for path in self._historyFiles():
            try:
                img = openImage(path, ["PNG"]).convert("RGB")
                img.thumbnail((240, 144))
            except InputError:
                continue
            items.append({"id": os.path.basename(path), "thumb": imageToDataUrl(img, "JPEG", quality=85), "time": os.path.getmtime(path)})
        return items

    def historyImage(self, id):
        path = self._historyPath(id)
        return self._readImage(path) if path else {"error": "Not found"}

    def historyDelete(self, id):
        path = self._historyPath(id)
        if path:
            os.remove(path)
        return True

    def _push(self, fn, value):
        if self._window:
            self._window.evaluate_js(f"window.{fn} && window.{fn}({json.dumps(value)})")

    def _readImage(self, path):
        if not regularFile(path):
            return {"error": "Can't open"}
        try:
            img = openImage(path)
        except InputError as e:
            return {"error": str(e)}
        buf = io.BytesIO()
        img.convert("RGBA").save(buf, "PNG")
        return {"name": os.path.basename(path), "url": dataUrl(buf.getvalue(), "image/png"), "width": img.width, "height": img.height}

    def _sendWorker(self, data):
        try:
            img = openImage(io.BytesIO(data), ["PNG"]).convert("RGB")
            if img.size != (deck.width, deck.height):
                img = deck.fitImage(img)
            size = deck.sendLogo(img, progress=lambda p: self._push("onSendProgress", round(p, 3)))
            self._saveHistory(img)
            result = {"ok": True, "bytes": size}
        except InputError as e:
            result = {"error": str(e)}
        except deck.DeckError as e:
            result = {"error": {"no deck": "No deck", "no access": "No access", "no ack": "No reply"}.get(str(e), "Failed")}
        except Exception:
            result = {"error": "Failed"}
        finally:
            self._sendLock.release()
        self._push("onSendDone", result)

    def _historyPath(self, id):
        if not isinstance(id, str) or not historyName.match(id):
            return None
        path = os.path.join(historyDir, id)
        try:
            st = os.lstat(path)
        except OSError:
            return None
        return path if stat.S_ISREG(st.st_mode) else None

    def _historyFiles(self):
        if not os.path.isdir(historyDir):
            return []
        files = [p for p in (self._historyPath(n) for n in os.listdir(historyDir)) if p]
        return sorted(files, key=os.path.getmtime, reverse=True)

    def _saveHistory(self, img):
        buf = io.BytesIO()
        img.save(buf, "PNG")
        data = buf.getvalue()
        digest = hashlib.sha256(data).digest()
        with self._fileLock:
            privateDir(appData)
            privateDir(historyDir)
            for path in self._historyFiles():
                if os.path.getsize(path) == len(data) and hashlib.sha256(open(path, "rb").read()).digest() == digest:
                    os.utime(path)
                    return
            writePrivate(os.path.join(historyDir, f"{int(time.time() * 1000)}.png"), data)
            for old in self._historyFiles()[historyMax:]:
                os.remove(old)


def page():
    def read(name):
        with open(os.path.join(webDir, name), encoding="utf-8") as f:
            return f.read()

    script = read("app.js")
    scriptHash = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    csp = "; ".join([
        "default-src 'none'",
        f"script-src 'sha256-{scriptHash}' 'unsafe-eval'",
        "style-src 'unsafe-inline'",
        "img-src data: blob:",
        "font-src data:",
        "connect-src 'none'",
        "media-src 'none'",
        "object-src 'none'",
        "frame-src 'none'",
        "worker-src 'none'",
        "form-action 'none'",
        "base-uri 'none'",
    ])
    html = read("index.html")
    html = html.replace('<meta charset="utf-8">', f'<meta charset="utf-8">\n<meta http-equiv="Content-Security-Policy" content="{csp}">', 1)
    html = html.replace('<link rel="stylesheet" href="style.css">', "<style>" + read("style.css") + "</style>", 1)
    html = html.replace('<script src="app.js"></script>', "<script>" + script + "</script>", 1)
    return html


def gui(args):
    import webview
    api = Api()
    window = webview.create_window("splashdeck", html=page(), js_api=api, width=1180, height=760, min_size=(960, 640), background_color="#0a0a0a", text_select=False)
    api._window = window
    initial = args[0] if args else None

    def ready():
        result = api._readImage(initial) if initial else api.wallpaper()
        if result and "url" in result:
            window.evaluate_js(f"window.loadInitial && window.loadInitial({json.dumps(result)})")

    window.events.loaded += ready
    privateDir(appData)
    tightenStorage()
    webview.start(gui="gtk", debug=False, private_mode=True)


def cli(args):
    if len(args) < 2 or (len(args) > 2 and args[2] not in modes):
        sys.exit("usage: splashdeck --send <image> [fill|fit|stretch]")
    if not regularFile(args[1]):
        sys.exit("can't open")
    try:
        deck.sendLogo(deck.fitImage(openImage(args[1]), args[2] if len(args) > 2 else "fill"))
    except InputError as e:
        sys.exit(str(e).lower())
    except (deck.DeckError, OSError) as e:
        sys.exit(str(e))
    print("sent")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--send":
        cli(args)
    elif args and args[0] in ("-h", "--help"):
        print("usage: splashdeck [image]\n       splashdeck --send <image> [fill|fit|stretch]")
    elif args and args[0] in ("-V", "--version"):
        print(__version__)
    else:
        gui(args)
