# RoyVa

RoyVa is the Roy family's personal assistant, built on vanilla OpenCode.
The name can be read as **Roy Virtual Assistant**.

Current runtime:

- Local **Qwen3.6-35B-A3B Q8_0**, reasoning off, no MTP. Two 131,072-token
  slots with prefix caching. The Flash launcher remains available offline;
  compatibility model IDs all address the single currently loaded model.
- Telegram text and voice input. Standalone messages create sessions; replies
  continue or steer the referenced session. Voice questions are transcribed
  first; progress and answers reply to the transcription. Final replies exclude
  intermediate model narration.
- Home Assistant native controls, a read-only history/status helper, and the
  configuration MCP. History accepts explicit timezone-aware date ranges in
  one query, with no seven-day tool limit. Zone intervals are not verified visits.
- Gmail through the active [Gmail MCP](components/gmail-active/README.md).
  List/search results include exact page counts, pagination flags and nullable
  approximate totals. Additional pages remain a separate user decision.
- Parallel websearch and native OpenCode webfetch. No custom search/fetch
  extraction adapter is deployed.
- Feedback buttons record answer-specific feedback/consent privately; they do
  not train a model or automatically change prompts.

## Instructions and tool exposure

Four instruction files cover identity/source selection, HA access and read/action
separation, structured evidence handling, and the goodnight automation shortcut.
Three supported plugins are active:

- [skill-catalog](components/skill-catalog): constrains skill IDs to the current catalogue.
- [time-context](components/time-context): appends refreshed local date/timezone guidance.
- [ha-config-access](components/ha-config-access): exposes automation create/read/remove
  and the HA guide directly. Other 68 allowed configuration tools remain in Code Mode;
  five overlapping configuration tools remain denied.

HA configuration writes are available, but free-form model scheduling is not
reliable: the model has rounded requested times and produced invalid configs.
Prompt rules do not enforce action scope. An unscoped native light command caused
an unintended broad action; a code-enforced scope guard has been audited but is
not implemented. The goodnight shortcut remains an explicitly authorized action.

## Deployment and source copies

OpenCode upstream remains unmodified at v2.2.5, commit
`9bbb8ce18c80f099e0e448775f59d965ead40a21`.
The live custom sources are in the separate clean OpenCode checkout; this repository
records source and deployment configuration. Paths are deployment-specific.
Private credentials, tokens, mailbox data, sessions, model weights, dependencies,
build outputs and benchmark payloads are excluded.

- [Telegram deployment](components/telegram-vanilla/README.md)
- [HA history/status interface](components/ha-legacy/README.md)
- [HA MCP package patches](components/ha-mcp/README.md): attribute-free history
  without record-compacting mode, and configuration-only guide loading.
- [Active Gmail source and count contract](components/gmail-active/ROYVA-COUNTS.md)
- [Separate prepared Gmail source](components/gmail-mcp/ROYVA-SETUP.md): inactive
  alternative with dependency/OAuth hardening. It is not the working Gmail runtime;
  do not replace the active connection merely because this copy exists.

Gmail write/draft/label tools have ask rules in the current configuration. Older
sessions may retain different permissions; blanket approval enforcement has not
been established. No email mutations are made by the count-verification tests.

## Focused validation

Use Node 24:

```sh
node --test components/telegram-vanilla/bridge.test.mjs components/skill-catalog/index.test.mjs components/time-context/index.test.js components/ha-config-access/index.test.js
node --check components/telegram-vanilla/bridge.mjs
```

For Gmail, install dependencies and build inside its component directory, then run
`node --experimental-test-module-mocks --test tests/counts.test.mjs`.
The voice-routing fixture mocks speech recognition and external APIs; it does not
constitute a live speech-recognition test. Tool-output limits remain upstream defaults.
