# checkmk-hetzner-storagebox

![License](https://img.shields.io/badge/license-Apache-2.0-blue)
![Checkmk](https://img.shields.io/badge/Tested%20with-Checkmk%202.4.0-green)
![Status](https://img.shields.io/badge/status-beta-orange)

Check for monitoring Hetzner Storage Boxes

---

## Overview

This Checkmk extension provides:

- Special agent execution from Checkmk server side
- Agent section parsing and service discovery
- Check logic with thresholds and metrics
- Ruleset integration for agent and check parameters

---

## Compatibility

Tested with:

- Checkmk 2.4.0

Compatible with:

- CEE
- CRE

---

## Features

- Configurable API target, credentials and timeout
- TLS verification toggle for self-signed certificates
- Threshold handling (`warn`/`crit`)
- Basic performance metric output

---

## Prerequisites

- Reachable target system/API endpoint
- Credentials with required permissions

---

## Installation (MKP)

1. Build or download the `.mkp` package.
2. Install package in site context:

```bash
mkp add hetzner_storagebox-<version>.mkp
mkp enable hetzner_storagebox
omd restart
```

---

## Manual Installation

Copy the plugin structure into:

```text
local/lib/python3/cmk_addons/plugins/
```

Then reload the site:

```bash
cmk -R
```

---

## Rule Configuration

### Special Agent Rule

Rule name: `hetzner_storagebox`

Parameters:

- `url`
- `username`
- `password`
- `timeout`
- `insecure`

### Check Parameters Rule

Rule name: `hetzner_storagebox`

Parameters:

- `warn`
- `crit`

---

## Metrics

- `value`

---

## Error Handling

CRIT is returned if:

- No data is received
- Agent output format is invalid
- Received value cannot be parsed

---

## Security

- HTTPS supported
- Optional TLS verification disable (`insecure`)
- Password is handled via Checkmk ruleset secret field

---

## Support

No commercial support.

Issues and Pull Requests welcome.

---

## Author

Manuel "Overlord" Michalski <www.47k.de>
