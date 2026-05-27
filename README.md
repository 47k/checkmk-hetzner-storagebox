# checkmk-hetzner-storagebox

![License](https://img.shields.io/badge/license-Apache-2.0-blue)
![Checkmk](https://img.shields.io/badge/Checkmk-2.x-green)
![Status](https://img.shields.io/badge/status-beta-orange)

Checkmk 2.x MKP plugin for monitoring Hetzner Storage Boxes through the Hetzner Console API.

## Purpose

The package adds a Checkmk special agent, discovery, check plugin, WATO rulesets, and metrics for Hetzner Storage Boxes. It discovers one service per Storage Box and monitors:

- API/storage box status
- Storage usage percentage and bytes
- Data and snapshot byte usage
- Snapshot count
- Subaccount count
- Optional thresholds for snapshot size, snapshot count, and subaccount count

## API Requirements

Create a Hetzner Console API token with permission to read Storage Boxes. This plugin uses the Hetzner Console API, not the legacy Robot API and not the Cloud-only API.

Default API endpoint:

```text
https://api.hetzner.com/v1
```

Primary endpoint used by the agent:

```text
GET /storage_boxes
Authorization: Bearer <api_token>
```

Additional endpoint used by default to count subaccounts:

```text
GET /storage_boxes/{id}/subaccounts
Authorization: Bearer <api_token>
```

The agent follows `meta.pagination` / `pagination` information when the API returns paginated responses for Storage Boxes and subaccounts.

## API Test

You can test the token outside Checkmk with:

```bash
curl -sS \
  -H "Authorization: Bearer $HETZNER_API_TOKEN" \
  -H "Accept: application/json" \
  https://api.hetzner.com/v1/storage_boxes
```

Subaccount counting can be tested for one Storage Box ID with:

```bash
curl -sS \
  -H "Authorization: Bearer $HETZNER_API_TOKEN" \
  -H "Accept: application/json" \
  https://api.hetzner.com/v1/storage_boxes/12345/subaccounts
```

## Installation

Build or download the MKP package, then install it as the Checkmk site user:

```bash
mkp add hetzner_storagebox-0.1.0.mkp
mkp enable hetzner_storagebox
cmk -R
```

For manual development installs, copy the `cmk_addons/plugins/hetzner_storagebox` tree into:

```text
~/local/lib/python3/cmk_addons/plugins/
```

Then reload Checkmk:

```bash
cmk -R
```

## Checkmk Setup

1. Go to Setup > Agents > Other integrations.
2. Create a rule for `Hetzner Storage Box`.
3. Enter the Hetzner Console API token in the password field.
4. Keep the API URL as `https://api.hetzner.com/v1` unless you have a compatible override.
5. Set the timeout if needed.
6. Optionally restrict monitoring to selected Storage Box IDs.
7. Run service discovery on the target Checkmk host.
8. Optionally tune `Hetzner Storage Box` service parameters.

Default service parameter behavior:

- Storage usage WARN at 80%, CRIT at 90%.
- Snapshot size, snapshot count, and subaccount count thresholds are disabled unless configured.
- Subaccount counts are fetched automatically from the Storage Box subaccounts API.
- Non-active statuses are WARN.
- API collection errors are UNKNOWN by default. This avoids turning API, authentication, or network reachability issues into CRIT unless you choose that policy explicitly.
- API collection error severity is configurable as UNKNOWN, WARN, or CRIT.

The service parameter ruleset includes options for storage usage, snapshot monitoring, and subaccount monitoring.

## Example Output

Special agent output uses one JSON payload inside a Checkmk section:

```text
<<<hetzner_storagebox:sep(0)>>>
{"storage_boxes":[{"id":12345,"username":"u12345","server":"fsn1-box1","status":"active","storage_box_type":{"name":"BX41","size":5497558138880},"stats":{"size":3485338895155,"size_data":3350074496614,"size_snapshots":135264398541},"subaccounts_count":6}],"errors":[]}
```

On API or network errors, the agent still emits a valid section:

```text
<<<hetzner_storagebox:sep(0)>>>
{"storage_boxes":[],"errors":[{"code":"auth_error","message":"HTTP 401 Unauthorized while fetching https://api.hetzner.com/v1/storage_boxes"}]}
```

Expected service output:

```text
OK - Used 63.4% (3.17 TiB / 5.00 TiB), Status: Active, Snapshot size 126.00 GiB, Snapshot count n/a, Subaccounts 6
```

The service details view uses multiline output:

```text
Used 63.4% (3.17 TiB / 5.00 TiB)
Status: Active
Snapshot size 126.00 GiB
Snapshot count n/a
Subaccounts 6
```

With optional thresholds configured, exceeded values produce additional WARN/CRIT results and annotate the details:

```text
WARN - Used 63.4% (3.17 TiB / 5.00 TiB), Status: Active, Snapshot size 120.00 GiB, Snapshot count 4, Subaccounts 6, Snapshot size: 120.00 GiB (WARN >= 100.00 GiB)
```

Details:

```text
Used 63.4% (3.17 TiB / 5.00 TiB)
Status: Active
Snapshot size: 120.00 GiB (WARN >= 100.00 GiB)
Snapshot count 4
Subaccounts 6
```

Discovery creates one service per returned Storage Box. It does not create a standalone API service:

```text
Hetzner Storage Box u12345
```

When the API returns partial data plus errors, each returned Storage Box service includes the API error at the configured severity. When no boxes can be returned because of an API error, discovery returns no new services. Already discovered Storage Box services remain stable and report the collection problem during check execution:

```text
Hetzner Storage Box u12345
UNKNOWN - API error (auth_error): HTTP 401 Unauthorized while fetching https://api.hetzner.com/v1/storage_boxes
```

If the API collection error severity is changed to CRIT, the same already discovered Storage Box service reports:

```text
Hetzner Storage Box u12345
CRIT - API error (auth_error): HTTP 401 Unauthorized while fetching https://api.hetzner.com/v1/storage_boxes
```

## Metrics

Each Storage Box service can emit the following perfdata when the API provides the corresponding fields:

- `used_bytes`
- `total_bytes`
- `used_percent`
- `data_bytes`
- `snapshots_bytes`
- `snapshots_count`
- `subaccounts_count`

Byte values are rendered in human-readable binary units such as GiB and TiB in the service summary.
When thresholds for snapshot size, snapshot count, or subaccount count are configured, the corresponding metric includes WARN/CRIT levels.

## Security

- The token is stored through the Checkmk password field.
- Server-side calls pass the token as a Checkmk `Secret`, so the command line receives a password-store reference rather than the token value.
- The special agent resolves the password-store reference at runtime.
- The token is never printed in normal output or structured error messages.

## Limitations

- The plugin depends on fields returned by `GET /storage_boxes`. Missing fields are handled gracefully, but missing storage size fields make usage evaluation UNKNOWN.
- `subaccounts_count` is not inferred from `GET /storage_boxes` or from `subaccounts_limit`. It is counted from `GET /storage_boxes/{id}/subaccounts` when subaccount fetching is enabled and the endpoint is available.
- Size metrics are interpreted as bytes, matching the Checkmk metric names and output units.
- The plugin monitors Storage Box metadata and capacity usage only. It does not test protocol-level access such as SSH, SFTP, SMB, Borg, or WebDAV.
- Filtering is by Storage Box ID, not username.

## Author

Manuel "Overlord" Michalski <www.47k.de>
