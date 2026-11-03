# Shellular - open-source remote control for your dev env

**Remotely access agents, terminals, code editor, localhost ports and browser DevTools from your phone.**

You don't move your workflow to your phone. You bring your existing machine as-is — desktop, laptop, Mac Mini, VPS, whatever — and access it from iOS, Android, or the web.

[![Download on the App Store](https://img.shields.io/badge/App_Store-000?logo=apple&logoColor=white)](https://apps.apple.com/app/shellular/id6761985327)
[![Get it on Google Play](https://img.shields.io/badge/Google_Play-000?logo=googleplay&logoColor=white)](https://play.google.com/store/apps/details?id=io.foxbiz.shellular)

## 📦 Source code

| Repository | What's inside |
| --- | --- |
| **[app](https://github.com/shellular-org/app)** | iOS / Android / web client |
| **[packages](https://github.com/shellular-org/packages)** | `shellular` CLI host agent + `@shellular/protocol` |
| **[server](https://github.com/shellular-org/server)** | WebSocket relay server |

## What it does

- **Access your actual local repos** — even with uncommitted changes
- **Run and interact with AI agents** — Claude Code, Codex, OpenCode, Pi & GitHub Copilot CLI, in a proper UI (not inside a terminal)
- **Open localhost apps and dev servers** running on your laptop or VPS, from your phone
- **Browser DevTools** — JS Console, Inspect, Network tab — copy error logs straight to your coding agents to fix
- **Plus terminal access** if you need it
- **File browser & editor** — browse, edit, and diff files with CodeMirror 6
- **System monitoring** — CPU, memory, and battery dashboards
- **Zero-config localhost access** — open the dev servers and apps running on your machine straight from the app, no port forwarding or tunnel setup

## Get started

1. Run `npx shellular` on your dev machine
2. Scan the QR code in the app (one time thing)
3. Approve your device in the CLI (one time thing)

That's it.

## Security

- **End-to-end encryption** — all messages encrypted with libsodium
- **QR code pairing** — the key is exchanged out-of-band and never travels over the network
- Traffic flows via **TLS-encrypted WebSockets**
- **Device approval required** — every unknown client must be approved before it can connect
- **Open-source relay server** — it only relays encrypted traffic, it cannot read it

## Architecture

```
┌─────────────┐        ┌──────────────┐        ┌─────────────────┐
│  app        │  E2E   │  server      │  E2E   │  packages/cli   │
│ (phone/web) │◄──────►│ (relay, wss) │◄──────►│ (host agent on  │
│             │        │              │        │  your dev box)  │
└─────────────┘        └──────────────┘        └─────────────────┘
```

The relay never sees plaintext — it only forwards libsodium-encrypted frames between the two paired endpoints.

## Run the CLI host agent

```bash
npx shellular
```

Scan the QR code printed in the terminal with the Shellular app to connect. See the [CLI README](https://github.com/shellular-org/packages/tree/main/cli) for daemon mode, client approval, and all available flags.

## Links

- [Website](https://shellular.dev)
- [X / Twitter](https://x.com/shellular_dev)
- [LinkedIn](https://linkedin.com/company/shellular)
- [App Store](https://apps.apple.com/app/shellular/id6761985327)
- [Google Play](https://play.google.com/store/apps/details?id=io.foxbiz.shellular)

## License

[AGPL-3.0-only](./LICENSE)
