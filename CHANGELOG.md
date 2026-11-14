# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- Strict Content Security Policy for the UI: scripts are allowed only by hash, no network access, no remote content
- Internal helpers are no longer callable from the UI; every exposed API call validates its input
- Image uploads from the UI must be PNG data and are size-limited
- Image files are limited to 64 MB and 64 megapixels, with decompression bomb protection
- Library entries are validated by name, so paths outside the library cannot be read or deleted
- Settings are filtered to known keys and types before being saved
- Settings and library are stored with owner-only permissions (directories `0700`, files `0600`), written atomically without following symlinks
- The device node is verified as the D6's hidraw character device before it is opened, with `O_CLOEXEC` and `O_NOFOLLOW`
- The web view runs in private mode with developer tools disabled
- External commands for wallpaper detection run without a shell, with a timeout and no stdin

## [0.2.0] - 2026-11-14

Initial public release.

### Added

- Set the splash screen on the fifine AmpliGame D6 over USB HID
- Image sources: file, drag and drop, clipboard, current desktop wallpaper (awww, swww, GNOME)
- Framing: fill, fit and stretch, pan, zoom, rotate and flip
- Fit backgrounds: black, white, blurred image, or a custom colour
- Brightness, contrast, saturation and grayscale adjustments
- Key overlay for the 15 keys
- Export to PNG
- Library of previously sent images
- Display page: live brightness, sleep, wake, show splash screen
- Device page: model, firmware, serial, USB port, permission check
- `--send` command line mode
- Nix flake, NixOS module, udev rule and desktop entry

[Unreleased]: https://github.com/owainxyz/splashdeck/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/owainxyz/splashdeck/releases/tag/v0.2.0
