# Protocol

This document describes the USB protocol used by the fifine AmpliGame D6, as observed by capturing traffic from the official fifine Control Deck software (version 3.10.201.0506) with `usbmon` while it ran in a Windows virtual machine.

The device is a MiraBox design and shares the general command format used by other HOTSPOTEK and Ajazz decks. Commands outside this document have not been verified on the D6.

## Device

| Property      | Value                       |
|---------------|-----------------------------|
| USB ID        | `3142:0060`                 |
| Manufacturer  | `HOTSPOTEKUSB`              |
| Product       | `HOTSPOTEKUSB HID DEMO`     |
| Speed         | High speed (480 Mb/s)       |
| Interface 0   | Vendor HID, usage page `0xFFA0` |
| Interface 1   | Boot keyboard               |
| Screen        | 800 × 480                   |

Interface 0 carries all commands. Its report descriptor declares 512-byte input reports and 1024-byte output reports with no report IDs.

## Framing

Every output report is exactly 1024 bytes, zero-padded. Shorter reports are ignored. When writing through `hidraw`, prefix the report with a `0x00` report ID byte, for a 1025-byte write.

Commands start with the 5-byte prefix `43 52 54 00 00` (`CRT\0\0`) followed by a three-letter verb and its arguments.

Input reports from the device start with `41 43 4B 00 00 4F 4B` (`ACK\0\0OK`).

## Splash screen

| Step | Direction | Data                                              |
|------|-----------|---------------------------------------------------|
| 1    | Out       | `CRT\0\0LOG` + length (u32, big-endian) + `00`    |
| 2    |           | Wait ~3 s while the device erases flash           |
| 3    | Out       | JPEG bytes, 1024 per report, last report padded   |
| 4    | In        | `ACK\0\0OK`                                       |
| 5    | Out       | `CRT\0\0STP`                                      |

Requirements for the JPEG:

- 800 × 480 pixels
- Baseline (not progressive)
- YCbCr 4:2:0 subsampling
- Rotated 180° relative to how it should appear on the device

The official software encodes at quality 100. The image persists across power cycles.

### Showing the image immediately

After the upload the device keeps showing whatever it showed before. To switch to the new image:

| Step | Data                  | Effect                            |
|------|-----------------------|-----------------------------------|
| 1    | `CRT\0\0DIS`          | Wake the screen                   |
| 2    | `CRT\0\0CLE\0\0DC`    | Clear and return to standby image |

## Display

| Command    | Data                                 | Notes                         |
|------------|--------------------------------------|-------------------------------|
| Brightness | `CRT\0\0LIG\0\0` + one byte          | 0 to 100                      |
| Wake       | `CRT\0\0DIS`                         |                               |
| Sleep      | `CRT\0\0HAN`                         | Screen off until `DIS`        |
| Clear all  | `CRT\0\0CLE\0\0\0` + `FF`            | Used by the official software |
| Flush      | `CRT\0\0STP`                         | Commit pending changes        |
| Keep-alive | `CRT\0\0CONNECT`                     | Sent every 10 s by the official software |

## Firmware version

Read HID feature report `0x01` (512 bytes) on interface 0. The response is a NUL-terminated ASCII string such as `V3.D6.1.009`.

On Linux this is the `HIDIOCGFEATURE` ioctl on the hidraw node.

## Capturing traffic

To verify a command against the official software:

1. Pass the device through to a Windows VM (for example a libvirt `hostdev` entry for `3142:0060`).
2. On the host, load `usbmon` and capture the bus: `tcpdump -i usbmonN -w capture.pcap`.
3. Perform the action in the official software.
4. Filter the capture to the device address and endpoint `0x03` (out) and `0x82` (in).

The host sees the traffic because QEMU forwards the device through usbfs.
