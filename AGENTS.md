# AGENTS.md

Guidance for coding agents working in this repository.

## Overview

splashdeck is a Linux app for the fifine AmpliGame D6 stream deck (USB `3142:0060`). It sets the device's splash screen and controls its display over USB HID. Python handles the device and exposes an API to a web UI rendered by pywebview (WebKitGTK).

## Layout

- `splashdeck/deck.py`: protocol. `findDeck`, `fitImage`, `encode`, `sendLogo`, `setBrightness`, `sleepScreen`, `wakeScreen`, `showLogoNow`, `deviceInfo`.
- `splashdeck/app.py`: `Api` class (methods are callable from JS as `window.pywebview.api.*`), `currentWallpaper`, `gui`, `cli`, `main`.
- `splashdeck/web/`: `index.html`, `style.css`, `app.js`. These are inlined into one HTML string at launch by `page()` in `app.py`, so WebKit never serves stale cached files.
- `flake.nix`: package (`packages.default`) and NixOS module (`nixosModules.default`).

## Build and run

```sh
nix build
./result/bin/splashdeck
./result/bin/splashdeck --send image.png fill
```

Without a display, test the UI under Xvfb:

```sh
Xvfb :99 -screen 0 1180x760x24 &
DISPLAY=:99 GDK_BACKEND=x11 WEBKIT_DISABLE_DMABUF_RENDERER=1 LIBGL_ALWAYS_SOFTWARE=1 ./result/bin/splashdeck
```

Unset `WAYLAND_DISPLAY` when doing this so the window does not open on a real desktop.

## Conventions

- camelCase names in Python and JavaScript
- No comments or docstrings
- UI copy is minimal: labels and one or two word statuses
- UI is monochrome (black and greys), dark only; no coloured accents or status dots
- Keep `--send` working without the GUI dependencies being used

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

## Before finishing a change

- `nix build` succeeds
- The app starts and every page renders with and without a device
- `CHANGELOG.md` is updated under **Unreleased** for user-facing changes
