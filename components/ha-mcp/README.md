# RoyVa HA MCP patches

Base package: `ha-mcp==9.1.0`. The server runs as local Python under
`royva-ha-mcp.service`; upstream OpenCode remains unmodified.

## Changes

- `patches/ha-mcp-guide-scope.patch`: narrows guide loading to configuration
  work. The guide body and server-enforced write checks remain unchanged.
- `patches/ha-mcp-compact-history.patch`: removes the model-facing
  `minimal_response` argument. History uses full recorder mode with
  `no_attributes=True`, and removes residual empty attributes from returned
  rows. States, timestamps, row counts and pagination remain available.
  Statistics behavior is unchanged. Historical attributes are intentionally
  unavailable through this patched history tool.

Do not replace this with `minimal_response=True`: Home Assistant's minimal
mode can reduce recorder rows, beyond removing attributes. This patch also
neither selects a canonical entity nor prevents querying multiple sources.

## Applying to a fresh installation

Install the pinned package in a virtual environment. From this directory,
set the target to that environment's site-packages directory:

```sh
HA_SITE=/path/to/venv/lib/python3.14/site-packages
patch --dry-run --fuzz=0 -d "$HA_SITE" -p1 < patches/ha-mcp-guide-scope.patch
patch --fuzz=0 -d "$HA_SITE" -p1 < patches/ha-mcp-guide-scope.patch
patch --dry-run --fuzz=0 -d "$HA_SITE" -p1 < patches/ha-mcp-compact-history.patch
patch --fuzz=0 -d "$HA_SITE" -p1 < patches/ha-mcp-compact-history.patch
```

Do not reapply to an already patched installation. A reverse dry run
(`patch --dry-run --reverse --fuzz=0 ...`) can check whether a patch is
already present. Review both patches when upgrading HA MCP; reinstalling
can overwrite local package changes.

Restart HA MCP and OpenCode to refresh tool metadata. Following any model
and OpenCode restart, wait for readiness and then at least 45 seconds before
starting an inference test.

## Verification

Check that the advertised history arguments omit `minimal_response`, and
that attempts to supply it are rejected. Compare a fixed entity/time window
against unpatched full-record mode: state and both timestamp fields, record
counts and pagination must match, while attributes must be absent. Check
multiple pages. These checks have passed against the deployed server.

Deployment service configuration is under `../systemd`. Credentials,
recordings, entity histories and benchmark outputs are not included here.
