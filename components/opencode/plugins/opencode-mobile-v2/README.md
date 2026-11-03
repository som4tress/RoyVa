# opencode-mobile-v2 (compatibility shim)

A local OpenCode **V2** wrapper around the V1-only
[`opencode-mobile`](https://github.com/doza62/opencode-mobile) plugin
(npm `opencode-mobile@1.4.0`), which cannot load on OpenCode v2 as-is
(upstream issue: doza62/opencode-mobile#37 — "Plugin must export a default
definition with an id and an effect or setup function").

## What it does

- Finds the newest `opencode-mobile` install in OpenCode's plugin cache
  (`~/.cache/opencode/npm/opencode-mobile@latest/*/node_modules/...`) at load time.
- Runs the V1 plugin's setup against the V2 plugin context (it only reads
  `ctx?.client` / `ctx?.serverUrl`, so this is safe).
- Re-registers the V1 `mobile` tool through V2's `ctx.tool.transform()`.
- Forwards V2 server events to the V1 event hook via `ctx.event.subscribe()`.

The V1 plugin itself only starts its LAN server (port OpenCode+1) and a tunnel
when OpenCode runs in `opencode serve` mode; otherwise it just provides the
`mobile` tool (QR code / push-token registration).

## Maintenance

- If the plugin cache is ever cleared, re-materialize it with:
  `opencode plugin add opencode-mobile@latest` (leave it out of the `plugins`
  config array to avoid V1 load-failure warnings), then `/reload`.
- If upstream ships a V2-native release, delete this shim and use the package
  directly.
