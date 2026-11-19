# img_video agent

Turns a query into a narrated video made of generated pictures: **query -> narration notes (web research, optional) -> pictures -> voice -> stitched video**.
It is its own agent: it has its own folder, config, job store and CLI, and it talks to everything else only through interfaces (HTTP or subprocess), so it can later run by itself.
RoyVa starts it through a thin tool wrapper (`submit`, `status`, `result`, `continue`, `cancel`); nothing here imports RoyVa code.

| Needs | How it is reached | Config |
|---|---|---|
| writer model (Qwen3.6-35B-A3B, this machine) | OpenAI-compatible HTTP, `llm` section | `config.toml`, key file path only |
| web research for facts (narration only) | provider interface; today the RoyVa gateway `/v1/ask` as identity `agent:img_video` | `research` |
| pictures (FLUX.2 klein text-to-image) | ComfyUI HTTP on the 3090 box | `comfy` |
| voice (Chatterbox) | subprocess in its own venv, runs on this machine's CPU | `tts` |
| stitching | ffmpeg on this machine | `video` |

Rules: no fixed counts or timings in code (they come from `capabilities.json`, measured, or from the narration itself); a stage re-runs only when the fingerprint of its inputs changes (never "file exists"); model names are checked against ComfyUI before any GPU work.
Jobs live in `jobs/<id>/` (git-ignored). Commands: `python -m img_video --help`.

## How RoyVa starts it (wired 2026-11-16)
- `mcp/img_video/server.py`: thin MCP wrapper, tool `generate_image_set(query, count, aspect)`; runs `python -m img_video run ... --json`, copies the pictures into `runtime/data/images/imgset-<job>-NN.png` (the only folder the bridge uploads from) and returns one text part per picture.
- Registered in: `config/opencode.json` (server `img-video`), `gateway/registry/tools.json` (`image.set`), `gateway/registry/intents/image_set.json` (active, write_policy auto; `image_generate` now says sets are not its job), `gateway/royva_gateway/config.py` (`expected_mcp`), `gateway/eval/eval_set.jsonl` (e146-e153).
- Bridge (`bridge/images.mjs`): recognizes `generate_image_set`; `sendPhotos` now paces sends (`ROYVA_PHOTO_GAP_MS`, default 2000), keeps a shared Telegram flood gate checked before every send and honors the full `retry_after` (up to 180 s), and keeps going after a failed picture.
- To take effect: `systemctl --user restart royva-opencode.service royva-gateway.service royva-bridge.service` (order is enforced by the units).
- Tests: `python3 -m unittest mcp.img_video.test_server` (from RoyVa/), `gateway/.venv/bin/python -m pytest` (330), `node --test bridge/*.test.mjs` (79).


## Animation stages (video)

`python3 -m img_video run "<query>" --count N --aspect 1:1 --video` (or `--job <id> --video` on a finished image set) adds four resumable stages after the pictures:

| Stage | Where | What |
|---|---|---|
| `storyboard` | local LLM | one shot per picture: a motion prompt and a narration line, each line limited to the character budget (from capabilities: clip length x max slow-down - padding, x measured speaking rate) |
| `voice` | this machine's CPU, in a thread | Chatterbox through `voice_worker.py` in the TTS venv, one wav per line |
| `clips` | ComfyUI box | Wan 2.2 14B image-to-video, locked INT8 stack named in `[wan]`, two-job batch (high-noise expert, then low-noise expert), never `/free`, refuses while the box is busy; runs at the same time as `voice` |
| `video` | this machine's CPU | per shot: slow the clip by at most `max_slow` to fit the line, interpolate to 24 fps, add the voice; then cross-dissolve all shots (`padding.crossfade_seconds`) |

Output is `<job>/video/video.mp4` plus `<job>/video.json` (length, size in MB, shots whose line had to be cut). Sizes per aspect are in `capabilities.json` (`video.sizes`).
Measured on the rainbow set (10 shots, 1:1, 432x432): storyboard 13 s, voice 83 s (hidden behind the clips), clips 253 s (image upload 2.9 s, high-noise 97 s, latents back to the box 9 s, low-noise 144 s), assembly 8 s: about 280 s for a 48 s video.
Not built yet: talking-presenter shots (speech-to-video), an asynchronous submit/status tool for RoyVa, and delivery of the mp4 through the bridge.


## All picture and video requests go through this agent (2026-11-17)
RoyVa's tools `image.generate`, `image.video` and `image.set` (MCP `mcp/img_video`) now call this agent; `mcp/image` only edits photos on this machine's GPU. Commands:
- `python3 -m img_video image "<prompt>" [--aspect 1:1|9:16|16:9] [--size WxH] [--seed N] --json`: ONE picture in the user's own words, no director. A prompt over `[limits] image_prompt_chars` is shortened by `guard.fit_prompt` (local writer, then a word-boundary cut). Drawn on the 3090 under the shared GPU lock; this machine's GPU is the fallback.
- `python3 -m img_video run "<query>" [--count N] [--video] --json`: the director. A set of pictures, or with `--video` a video. The planner decides `narrated` (voice-over for an explanation, silent for a pure clip); a silent video has no voice stage and no audio track. The director writes a motion line only for videos and a narration line only for narrated videos.
- `python3 -m img_video fit "<prompt>" --json`: just the shortening step.
RoyVa starts sets and videos in the background (`mcp/img_video/runner.py`): the tool returns at once, the result lands in `runtime/data/outbox/done/<job>.json` and the Telegram bridge (`bridge/outbox.mjs`) posts it to the chat that asked. Guards: `guard.py` (hard ceiling `[limits] hard_prompt_chars` on every text-encoder input of every graph posted by `comfy._call` and `wan.py`, and the one-job-at-a-time lock `runtime/gateway/gpu3090.lock`). The old ComfyUI client of the chat tool lives on in `runtime/episodes/lib/` for the old experiment scripts only.
