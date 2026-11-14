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

## Scope

splashdeck runs locally and does not open network ports. Areas of interest include:

- The udev rule and device permissions
- Handling of untrusted image files
- The bridge between the web UI and Python (`splashdeck/app.py`)
