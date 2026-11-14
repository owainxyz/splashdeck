# Troubleshooting

## The app says "No deck"

- Check the device is connected: `lsusb | grep 3142:0060`
- Try another USB port, preferably one directly on the computer rather than a hub. Some hubs fail to enumerate the device (`device not accepting address` in `dmesg`).
- Make sure the official software is not running in a VM with the device passed through.

## The app says "No access"

Your user cannot open the device node. Install the udev rule:

```sh
sudo cp 60-splashdeck.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger
```

Then reconnect the device. On NixOS, use the module from the flake, or add the rule to `services.udev.extraRules`.

The rule uses `TAG+="uaccess"`, which grants access to the user of the active local session. If you log in without a session manager that registers seats (for example a bare TTY login starting a compositor), replace it with `MODE="0666"`.

## The app says "No reply"

The device did not acknowledge the upload. Reconnect it and try again. If it keeps happening, open a bug report with your firmware version.

## The screen stays off after sending

Use **Display → Wake**, or send again; recent versions wake the screen automatically after an upload.

## The image appears upside down or mirrored

Make sure you are on the latest version. The image must be rotated 180° before upload; splashdeck does this for you, so do not rotate it yourself unless the source image is wrong.

## The window is blank

pywebview needs WebKitGTK 4.1. Install it from your distribution (`webkit2gtk4.1`, `libwebkit2gtk-4.1-0` or similar). On systems with GPU driver issues, try:

```sh
WEBKIT_DISABLE_DMABUF_RENDERER=1 splashdeck
```
