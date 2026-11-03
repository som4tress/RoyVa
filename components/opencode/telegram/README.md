# Telegram ↔ OpenCode Bridge

Talk to OpenCode from your phone via **@roy_has_bot**. Every message you send
becomes a prompt to OpenCode; replies come back in the chat. Home Assistant
tools are attached, so the bot is also a remote control for the house.

- **Model:** `openrouter/deepseek/deepseek-v4.1-flash-1017` (pinned)
- **Owner:** Telegram user `6064019420` (allowlisted; all others rejected)
- **Transport:** long polling — outbound HTTPS only, no open ports, no webhook

## Files

| File | Purpose |
|---|---|
| `bridge.mjs` | The bridge (Telegram long-poll → `opencode run` → reply) |
| `bot.env` | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_USER_IDS` (mode 600) |
| `state.json` | Telegram update offset + OpenCode session id per chat |
| `README.md` | This file |

Log: `~/.local/state/opencode/telegram-bridge.log`

## How it works

1. Long-polls Telegram for new messages.
2. Checks sender against the allowlist in `bot.env`.
3. Spawns `opencode run --format json -m <model> -s <session>` with the message.
4. Streams the JSON events, keeps the final assistant text, sends it back
   (split into 3900-char chunks if long). Shows "typing…" while working.

General chat keeps its persistent session. Atomic HA text requests use fresh sessions to avoid long-history compaction. Pronoun follow-ups carry only the previous HA question/answer and up to six bounded tool input references, expiring after 30 minutes. `/new` clears both general context and HA carryover. Local HA inference has a shared 60-second turn deadline, including compaction, then one-way DeepSeek fallback; cloud completion time is additional.

## Voice notes (Whisper)

Send a 🎤 voice note instead of typing — it works exactly like a text message.

1. `bridge.mjs` downloads the clip from Telegram (`getFile` → `api.telegram.org/file`).
2. `ffmpeg` converts it to 16 kHz mono PCM WAV.
3. `whisper-cli` (whisper.cpp, CUDA build on the RTX 3090) transcribes with
   `ggml-large-v3-turbo-q5_0.bin`, language auto-detected (English/Hindi/…).
4. The transcript is echoed back (`🎤 "…"`), then sent to OpenCode as the prompt —
   so commands like "/new", "/status" also work spoken.

Nothing is uploaded to any transcription API; it all runs on this box.
If the GPU is unavailable (e.g. the driver isn't ready seconds after boot),
the bridge retries the same clip on the CPU backend (`-ng`) instead of failing.

**Files / env**

| Path | Purpose |
|---|---|
| `~/.local/share/opencode/whisper/bin/whisper-cli` | whisper.cpp binary (+ its `libggml*.so`) |
| `~/.local/share/opencode/whisper/models/ggml-large-v3-turbo-q5_0.bin` | 548 MB multilingual model |
| `install-whisper.sh` | rebuilds/reinstalls the above (CPU or CUDA) |

Overrides: `WHISPER_BIN`, `WHISPER_MODEL`, `WHISPER_LANG` (`auto` by default),
`WHISPER_PROMPT`, `WHISPER_TIMEOUT`, `FFMPEG_BIN`. Rebuild the model set with
e.g. `WHISPER_LANG=en` in the unit if you want English-only decoding.

**Vocabulary bias.** Transcription is primed with the house's entity/person names
(`Kitchen Dimmer`, `Island Dimmer`, `Den Switch`, `Shivi Room Fan`, `Pecky`,
`Shobha`, …) via whisper's initial prompt — without it the model writes
"shivvy room fan" and "Shabka", which then fail to match an entity. The prompt is
never echoed into the transcript. Override `WHISPER_PROMPT` to add your own names,
or set it empty (`WHISPER_PROMPT=`) to turn the bias off.

## Commands (in Telegram)

- `/new` — fresh session (forgets context)
- `/id` — show your user/chat id and allowlist status
- `/status` — model, working dir, session, pid
- `/help` — command list
- 🎤 voice note — transcribed locally, then treated as a normal prompt

Anything else is sent to the agent as a prompt.

## Ops

```bash
systemctl --user status   opencode-telegram.service   # is it running?
systemctl --user restart  opencode-telegram.service   # restart
journalctl --user -u      opencode-telegram.service   # systemd view
tail -f ~/.local/state/opencode/telegram-bridge.log   # live bridge log
```

The service is user-level and `enabled`, and the account has `Linger=yes`
(`loginctl enable-linger somdutta`) — so it starts **at boot**, without anyone
logging in, and `Restart=always` brings it back if the process dies.
Environment (incl. `HA_TOKEN` for the Home Assistant MCP server) comes from
`~/.config/environment.d/`.

```bash
loginctl show-user somdutta -p Linger        # Linger=yes  → starts at boot
systemctl --user is-enabled opencode-telegram.service   # enabled
```

## Security notes

- Only user `6064019420` is allowed; strangers get an automatic rejection.
- The agent runs with **full tool access as this user** (bash, file edits, and
  HA actuation). To go read-only, add a permission gate in `opencode.json` or
  run the agent with a restricted agent profile.
- Keep `bot.env` private (mode 600). Rotate the token via @BotFather and update
  `bot.env` + restart if it ever leaks.
