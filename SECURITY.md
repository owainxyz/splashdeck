# Security Policy

## Supported versions

Only the latest release receives fixes.

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes       |
| < 0.2   | No        |

## Reporting a vulnerability

Please do not open a public issue for security problems.

Report vulnerabilities privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Include:

- A description of the issue and its impact
- Steps to reproduce
- The version, distribution and install method you used

You can expect an initial response within a week. Once a fix is available it will be released and the report credited unless you ask otherwise.

## Security model

splashdeck runs locally as your user. It does not open network ports or make network requests.

- **UI isolation.** The interface is a local page inlined at launch under a strict Content Security Policy. Only the bundled script is allowed to run (by SHA-256 hash), and network, frames, workers and remote content are blocked. `unsafe-eval` is permitted because pywebview's JavaScript bridge requires it.
- **Minimal bridge.** Only the methods the UI needs are exposed to JavaScript. Each validates its arguments; helpers are private.
- **Untrusted images.** Files are size- and pixel-limited and decoded by Pillow with decompression bomb protection. Images coming from the UI must be PNG.
- **Local data.** Settings (`~/.config/splashdeck`) and the library (`~/.local/share/splashdeck`) are owner-only and written atomically without following symlinks.
- **Device access.** splashdeck only opens a hidraw node after confirming it is a character device belonging to the D6 (`3142:0060`, vendor interface). The bundled udev rule grants access to the active local session only (`uaccess`).

If your system does not support `uaccess`, prefer an owner-only rule over a world-writable one:

```
KERNEL=="hidraw*", ATTRS{idVendor}=="3142", ATTRS{idProduct}=="0060", OWNER="youruser", MODE="0600"
```

## Scope

splashdeck runs locally and does not open network ports. Areas of interest include:

- The udev rule and device permissions
- Handling of untrusted image files
- The bridge between the web UI and Python (`splashdeck/app.py`)
