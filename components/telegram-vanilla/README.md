# Telegram text and voice for vanilla OpenCode

Selective port from the existing Royva Telegram bridge: Bot API polling, text,
message chunking, whisper.cpp speech transcription, native session API, interruption,
permission replies, feedback buttons and token display. No legacy agents, prompts,
model routing, Home Assistant rules, learning execution or history transformations
are imported. The upstream OpenCode packages remain unchanged.

The sole custom identity instruction is `identity.md`: RoyVa is the Roy family's
personal AI assistant. It supplies no task policy or individual family names.

Standalone messages create a native session. Replying to an incoming or outgoing
message continues its mapped session in the same chat. `/stop` interrupts the
matching request; `/approve` and `/deny` reply to native permission requests.
`/help` and `/status` describe the interface. Voice notes are transcribed on the
existing whisper host, with no vocabulary prompt, then submitted as plain user text.
Replies are text; speech synthesis is not included.

Progress edits show elapsed time, native completed-pass token usage, cached input,
peak input and tool activity. While streaming, output is retokenized using the
active model's `/tokenize` endpoint and marked approximate; provider input totals
are pending until the pass reports usage. No invented live input counts or costs.

The `Accept & learn` and `Incorrect` buttons append answer-specific feedback to
private `feedback.jsonl`. Acceptance records consent; it does not save a guide yet.
Incorrect sends a versioned, redacted bundle to DeepSeek through OpenRouter and
returns a validated `steer_only`, `build`, or `insufficient_evidence` classification.
The key is read at request time from `~/OpenRouter.txt` (or
`OPENROUTER_API_KEY_FILE`) and is never copied into the repository or logged.
This step does not yet execute recovery, build a capability, or save an accepted
guide. Tool schemas are captured privately from session context; a missing schema
is marked unavailable. A later vote supersedes the earlier vote for that answer
when consumers fold the ledger.

## Local deployment

- Source: `integrations/telegram` in the clean v2.2.5 checkout.
- Runtime: `~/.local/share/opencode-vanilla`, with separate config/data/state/cache.
- Native working directory: runtime `workspace`; project and Claude discovery disabled.
- OpenCode: existing v2.2.5 binary, SHA256
  `8d060e1d2fbb9bb44cf09ae6ed1f3f6a7cff070b5227e2f90970132b23a92050`.
  Using the matching installed release avoids rebuilding/upgrading upstream.
- Services: `opencode-vanilla.service` on loopback 49375 and
  `opencode-telegram-vanilla.service`, both user services.
- Model: local Qwen3.8-27B Q8_0, Q8 MTP companion, draft maximum 6,
  probabilistic draft sampling, reasoning off, prefix caching retained.
  Sampling follows https://huggingface.co/Qwen/Qwen3.8-27B.
- Bot token and explicit user allowlist are read from the existing private bot.env;
  model credential is read from api.env; native API password is private runtime.env.
  No credentials or previous conversation history are copied into this repository.
- Previous `opencode-telegram`, `opencode-evo` and `opencode-media-deadline` services
  are stopped and disabled. Their source and data remain available for recovery.
  `qwen38-eval` is stopped; the permanent llama service owns port 8000.
- Do not start a second poller for the same bot token.

Focused checks: `node --test integrations/telegram/bridge.test.mjs` and
`node --check integrations/telegram/bridge.mjs` (Node 24). Live checks cover native
text and follow-up history plus synthetic audio transcription. A user Telegram
exchange confirms external polling and text delivery. These checks do not claim
household tool, routing, cloud escalation or code execution validation.

An update is recorded as admitted before asynchronous execution. A process crash
can lose an in-flight update; it is deliberately not replayed automatically, which
could repeat actions. Sessions retain admitted native conversation and receipts.

## Image and video input

Photos, image/video documents, video messages and video notes now retain their
captions and reach the shared `media-input` integration. Single images use native
vision; videos use up to eight timestamped frames (20 MB / ten minute limit),
without audio transcription. Attachment-only messages are supported. Voice/audio
transcription and existing reply/steering behavior remain in place. The current
model is Qwen3.6-35B-A3B Q8_0 with its matching F16 vision projector; no MTP.
