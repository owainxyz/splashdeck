import base64, io, json, os, re, shutil, subprocess, sys, threading, time

from PIL import Image

from . import __version__, deck

modes = ["fill", "fit", "stretch"]
webDir = os.path.join(os.path.dirname(__file__), "web")
dataHome = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
configHome = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
historyDir = os.path.join(dataHome, "splashdeck", "history")
settingsPath = os.path.join(configHome, "splashdeck", "settings.json")
historyMax = 24
imageTypes = ("png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "gif")


def dataUrl(data, mime):
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def decodeDataUrl(url):
    return base64.b64decode(url.split(",", 1)[1])


def imageToDataUrl(img, fmt="PNG", **kw):
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return dataUrl(buf.getvalue(), "image/" + fmt.lower())


def currentWallpaper():
    for tool in ("awww", "swww"):
        if shutil.which(tool):
            try:
                out = subprocess.run([tool, "query"], capture_output=True, text=True, timeout=2).stdout
            except (OSError, subprocess.SubprocessError):
                out = ""
            m = re.search(r"image: (.+)$", out, re.M)
            if m and os.path.isfile(m.group(1).strip()):
                return m.group(1).strip()
    state = os.path.expanduser("~/.local/state/wallpaper")
    if os.path.isfile(state):
        path = open(state).read().strip()
        if os.path.isfile(path):
            return path
    if shutil.which("gsettings"):
        for key in ("picture-uri-dark", "picture-uri"):
            try:
                out = subprocess.run(["gsettings", "get", "org.gnome.desktop.background", key], capture_output=True, text=True, timeout=2).stdout.strip().strip("'")
            except (OSError, subprocess.SubprocessError):
                continue
            path = out.removeprefix("file://")
            if path and os.path.isfile(path):
                return path
    return None


class Api:
    def __init__(self):
        self.window = None
        self.sendLock = threading.Lock()

    def state(self):
        info = deck.deviceInfo()
        return {"version": __version__, "device": info}

    def settings(self):
        try:
            return json.load(open(settingsPath))
        except (OSError, ValueError):
            return {}

    def saveSettings(self, values):
        os.makedirs(os.path.dirname(settingsPath), exist_ok=True)
        current = self.settings()
        current.update(values)
        json.dump(current, open(settingsPath, "w"))
        return True

    def wallpaper(self):
        path = currentWallpaper()
        return self.readImage(path) if path else None

    def pickImage(self):
        import webview
        start = os.path.expanduser("~/Pictures")
        result = self.window.create_file_dialog(webview.OPEN_DIALOG, directory=start if os.path.isdir(start) else "", file_types=("Images (" + ";".join("*." + t for t in imageTypes) + ")", "All files (*.*)"))
        if not result:
            return None
        return self.readImage(result[0])

    def readImage(self, path):
        try:
            img = Image.open(path)
            img.load()
        except Exception:
            return {"error": "Can't open"}
        buf = io.BytesIO()
        img.convert("RGBA").save(buf, "PNG")
        return {"name": os.path.basename(path), "url": dataUrl(buf.getvalue(), "image/png"), "width": img.width, "height": img.height}

    def exportImage(self, url):
        import webview
        result = self.window.create_file_dialog(webview.SAVE_DIALOG, directory=os.path.expanduser("~"), save_filename="bootlogo.png")
        if not result:
            return False
        path = result if isinstance(result, str) else result[0]
        open(path, "wb").write(decodeDataUrl(url))
        return os.path.basename(path)

    def send(self, url):
        if not self.sendLock.acquire(blocking=False):
            return {"error": "Busy"}
        threading.Thread(target=self.sendWorker, args=(url,), daemon=True).start()
        return {"started": True}

    def push(self, fn, value):
        if self.window:
            self.window.evaluate_js(f"window.{fn} && window.{fn}({json.dumps(value)})")

    def sendWorker(self, url):
        try:
            img = Image.open(io.BytesIO(decodeDataUrl(url))).convert("RGB")
            if img.size != (deck.width, deck.height):
                img = deck.fitImage(img)
            size = deck.sendLogo(img, progress=lambda p: self.push("onSendProgress", round(p, 3)))
            self.saveHistory(img)
            result = {"ok": True, "bytes": size}
        except deck.DeckError as e:
            result = {"error": {"no deck": "No deck", "no access": "No access", "no ack": "No reply"}.get(str(e), str(e))}
        except Exception as e:
            result = {"error": str(e) or "Failed"}
        finally:
            self.sendLock.release()
        self.push("onSendDone", result)

    def control(self, action, value=None):
        try:
            if action == "brightness":
                deck.setBrightness(int(value))
                self.saveSettings({"brightness": int(value)})
            elif action == "sleep":
                deck.sleepScreen()
            elif action == "wake":
                deck.wakeScreen()
            elif action == "logo":
                deck.showLogoNow()
            return {"ok": True}
        except (deck.DeckError, OSError) as e:
            return {"error": str(e)}

    def saveHistory(self, img):
        os.makedirs(historyDir, exist_ok=True)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        data = buf.getvalue()
        for path in self.historyFiles():
            if os.path.getsize(path) == len(data) and open(path, "rb").read() == data:
                os.utime(path)
                return
        open(os.path.join(historyDir, f"{int(time.time() * 1000)}.png"), "wb").write(data)
        for old in self.historyFiles()[historyMax:]:
            os.remove(old)

    def historyFiles(self):
        if not os.path.isdir(historyDir):
            return []
        files = [os.path.join(historyDir, n) for n in os.listdir(historyDir) if n.endswith(".png")]
        return sorted(files, key=os.path.getmtime, reverse=True)

    def history(self):
        items = []
        for path in self.historyFiles():
            try:
                img = Image.open(path).convert("RGB")
                img.thumbnail((240, 144))
            except Exception:
                continue
            items.append({"id": os.path.basename(path), "thumb": imageToDataUrl(img, "JPEG", quality=85), "time": os.path.getmtime(path)})
        return items

    def historyImage(self, id):
        path = os.path.join(historyDir, os.path.basename(id))
        return self.readImage(path)

    def historyDelete(self, id):
        path = os.path.join(historyDir, os.path.basename(id))
        if os.path.isfile(path):
            os.remove(path)
        return True


def page():
    read = lambda n: open(os.path.join(webDir, n), encoding="utf-8").read()
    html = read("index.html")
    html = html.replace('<link rel="stylesheet" href="style.css">', "<style>" + read("style.css") + "</style>")
    html = html.replace('<script src="app.js"></script>', "<script>" + read("app.js") + "</script>")
    return html


def gui(args):
    import webview
    api = Api()
    window = webview.create_window("splashdeck", html=page(), js_api=api, width=1180, height=760, min_size=(960, 640), background_color="#0a0a0a", text_select=False)
    api.window = window
    initial = args[0] if args else None

    def ready():
        result = api.readImage(initial) if initial else api.wallpaper()
        if result and "url" in result:
            window.evaluate_js(f"window.loadInitial && window.loadInitial({json.dumps(result)})")

    window.events.loaded += ready
    webview.start(gui="gtk", private_mode=False, storage_path=os.path.join(dataHome, "splashdeck", "web"))


def cli(args):
    if len(args) < 2 or (len(args) > 2 and args[2] not in modes):
        sys.exit("usage: splashdeck --send <image> [fill|fit|stretch]")
    try:
        deck.sendLogo(deck.fitImage(Image.open(args[1]), args[2] if len(args) > 2 else "fill"))
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
