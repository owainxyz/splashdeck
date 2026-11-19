# Contributing to splashdeck

Thanks for your interest in improving splashdeck. Bug reports, device reports, and pull requests are all welcome.

## Ways to contribute

- **Report a bug** using the bug report template. Include your distribution, firmware version (shown on the Device page), and steps to reproduce.
- **Report a device.** If you have another Mirabox-based deck (Ajazz, fifine, MiraBox, or another HOTSPOTEK rebrand), open a device report with its USB ID, screen resolution, and whether sending a splash screen works.
- **Suggest a feature** using the feature request template.
- **Send a pull request** for fixes, features, or documentation.

## Development setup

### With Nix

```sh
git clone https://github.com/owainxyz/splashdeck
cd splashdeck
nix build
./result/bin/splashdeck
```

### Without Nix

Install WebKitGTK 4.1 and PyGObject from your distribution, then:

```sh
git clone https://github.com/owainxyz/splashdeck
cd splashdeck
python -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -e .
splashdeck
```

`--system-site-packages` lets the virtual environment use your distribution's PyGObject.

You also need the udev rule from [`60-splashdeck.rules`](60-splashdeck.rules) installed, or the app will report **No access**.

### Testing the UI headless

To test the UI under Xvfb:

```sh
Xvfb :99 -screen 0 1180x760x24 &
DISPLAY=:99 GDK_BACKEND=x11 WEBKIT_DISABLE_DMABUF_RENDERER=1 LIBGL_ALWAYS_SOFTWARE=1 ./result/bin/splashdeck
```

Unset `WAYLAND_DISPLAY` when doing this so the window does not open on a real desktop.

## Project layout

| Path                       | Purpose                                              |
|----------------------------|------------------------------------------------------|
| `splashdeck/deck.py`       | USB HID protocol: discovery, upload, display control |
| `splashdeck/app.py`        | Python API exposed to the UI, CLI entry point        |
| `splashdeck/web/`          | UI: `index.html`, `style.css`, `app.js`              |
| `flake.nix`                | Nix package and NixOS module                         |
| `60-splashdeck.rules`      | udev rule for unprivileged access                    |
| `docs/`                    | Protocol reference and troubleshooting               |

The UI renders the final 800 × 480 image in a canvas and hands a PNG to Python, which encodes and uploads it. The CLI (`--send`) uses Pillow for the same framing.

## Code style

- camelCase for functions and variables, in both Python and JavaScript
- Keep code self-explanatory; avoid comments and docstrings
- Four-space indentation in Python, two spaces in JavaScript, HTML, CSS and Nix (see [`.editorconfig`](.editorconfig))
- No new runtime dependencies without discussion
- UI text is short and functional: labels and one or two word status messages, no explanatory copy
- The UI is monochrome (black and greys); do not introduce accent colours
- Follow the security rules in the [rules below](#security-rules): keep the CSP strict, validate bridge input, use the provided helpers for files and the device

## Protocol rules

Read [`docs/PROTOCOL.md`](docs/PROTOCOL.md) before touching `deck.py`.

- Output reports are 1024 bytes plus a leading report ID byte (`0x00`) when written to hidraw; shorter reports are ignored by the device.
- After the `LOG` header, wait about 3 seconds before sending image data.
- The JPEG must be 800 × 480, baseline, 4:2:0, and rotated 180° before encoding.
- After uploading, `DIS`, `CLE\0\0DC`, `DIS` shows the image and keeps the screen awake. `HAN` puts the screen to sleep; do not send it as part of the upload flow.
- Do not add commands that write to flash unless they were captured from the official software and verified on hardware.

## UI to Python bridge

- Long operations must not block the JS promise. `Api.send` starts a worker thread and returns `{"started": true}`; progress and completion are pushed with `window.evaluate_js` to `window.onSendProgress` and `window.onSendDone`.
- Data crosses the bridge as data URLs. Keep payloads to a single image.
- Every public method on `Api` is callable from JavaScript. Prefix internal helpers with `_` so pywebview does not expose them, and validate every argument of public methods.

## Security rules

- Keep the Content Security Policy in `page()` strict. Do not add `unsafe-inline` to `script-src`, inline event handler attributes, or any network source.
- Render untrusted strings with `textContent`, never `innerHTML`.
- Open images through `openImage()` so size and pixel limits apply.
- Write user data with `writePrivate()` and create directories with `privateDir()`.
- Open the device only through `deck.openDeck()`.

## Testing

There is no automated test suite yet. Before opening a pull request:

1. Run `nix build` (or `pip install -e .`) and make sure the app starts.
2. If you changed `deck.py`, send an image with `splashdeck --send image.png` and confirm the device shows it.
3. If you changed the UI, check every page (Splash screen, Display, Device) with and without a device connected.

Please say in the pull request which device and firmware you tested on.

## Protocol changes

The device protocol was worked out by capturing USB traffic from the official Windows software. If you add or change a command:

- Document it in [`docs/PROTOCOL.md`](docs/PROTOCOL.md)
- Describe how you verified it (capture, testing on hardware)
- Never send commands you have not verified; a wrong flash command can leave the device in a bad state

## Commits and pull requests

- Keep pull requests focused on one change
- Write commit messages in the imperative mood, e.g. `Add brightness presets`
- Update `CHANGELOG.md` under **Unreleased** for user-facing changes
- Update the README if you change behaviour, options, or installation steps

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating you agree to uphold it.
