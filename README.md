# RoyVa

RoyVa is the Roy family's personal AI assistant, built on vanilla OpenCode.
The name can be read as **Roy Virtual Assistant**.

This repository starts fresh with the Telegram integration. It contains no
legacy Royva history, routing plugins, household policies or learning engine.

Current features:

- Telegram text and voice input, with native OpenCode sessions.
- Standalone messages create sessions; replies continue the referenced session.
- Live progress and token statistics, with approximate streaming counts labeled.
- Accept & learn / Incorrect buttons recording answer-specific feedback and consent.
- A minimal assistant identity: RoyVa, the Roy family's personal AI assistant.
- Local Qwen3.8 27B Q8_0 with reasoning off and MTP draft length 6.

See [integration documentation](components/telegram-vanilla/README.md) for deployment,
validation, feedback semantics and limitations. Services and configuration snapshots
use deployment-specific paths; private credentials and runtime data are excluded.

OpenCode upstream remains unmodified at v2.2.5, commit
`9bbb8ce18c80f099e0e448775f59d965ead40a21`.
The live transport source is currently in the separate clean OpenCode checkout;
this repository records its source and deployment configuration.

Run focused checks with Node 24:

```sh
node --test components/telegram-vanilla/bridge.test.mjs
node --check components/telegram-vanilla/bridge.mjs
```
