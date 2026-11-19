# Handoff, 2026-11-11: image skill as shipped, and the autonomous-agents idea

Read `HANDOFF.md` first (architecture, sections 1-12). This file covers what changed on 2026-11-10/11 and what is being thought through next. Nothing is pushed; all work is committed locally (last commit `f2a0acd`). The only uncommitted change is the intentional dummy Gmail entries in `config/opencode.json`.

## 1. State right now (all deployed and live)

- Stack: Telegram -> bridge -> gateway :8300 -> OpenCode :49380 -> llama.cpp (35B chat model + 9B router). Last `scripts/deploy.sh` passed all health checks.
- Tests: `scripts/check.sh` green (gateway 265, bridge 52). Route suite 95/95 (1 known xfail). Live suite last full run 93/95, the 2 failures were fixed and re-run 3x (see section 3); the 4 image live cases were re-run after the final deploy: 5/5 pass. A full live run has NOT been repeated since the last two fixes.
- Telegram listener: only armed when the owner asks (`scripts/claude-inbox-watch.sh` under Monitor, 30 min cap). Replies go through `scripts/notify.sh`. Standing rule: if something is needed from the owner, send it on Telegram; keep replies short.

## 2. Image skill (what exists)

Pipeline: message (photo saved to `runtime/data/inbox` by the bridge) -> gateway intent `image_generate` (tools: image.generate, image.edit, web.search, web.fetch; news memes search first) -> chat model writes an English prompt -> MCP server `image-gen` (`mcp/image/image_gen.py`, tools `generate_image`, `edit_image`) -> `sd-cli` (stable-diffusion.cpp master-1086, Vulkan) with Qwen-Image-2.1 Q8 GGUF + Qwen3-VL-8B Q8 text encoder + 2.1 VAE -> PNG in `runtime/data/images` -> bridge sends the picture BEFORE the text reply (own try/catch, Telegram 429 retry) -> usage footer.
- Editing: same model with `-r <photo>` + `--llm_vision mmproj-Qwen3-VL-8B-F16.gguf`; no separate denoise strength, the change is described in words. Output size follows the photo (long side <= 1024).
- Files outside the repo: `~/llm-server/sdcpp/master-1086/` (binary), `~/llm-server/models/image/qwen-image-2.1/` (16+ GB), benchmark scripts `~/llm-server/sdcpp/bench.sh`, `bench2.sh`, results in `~/llm-server/sdcpp/bench/`.
- Measured (Strix Halo, Vulkan, 1024x1024, same seed): sampling is 183 of 190 s (compute-bound, ~2 passes/step at cfg>1); text encoder + VAE ~4 s. Old default (20 steps, cfg 6.0) = ~190 s and had halos/oversaturation. **Current defaults: 30 steps, cfg 4.0, `--cache-mode easycache` = ~110-120 s, clean** (EasyCache skips ~18 of 30 steps). Overrides: `ROYVA_IMAGE_STEPS`, `ROYVA_IMAGE_CFG`, `ROYVA_IMAGE_CACHE` ("" disables). Flow-shift made no difference. 28 steps without cache = 263 s (not worth it).
- Sizes: multiples of 16, 512-1280 per side, so 1280x720 works. One render at a time (lock file); concurrent requests serialize.
- Text in pictures: the model garbles many/long texts. The intent style says: <=2 short ALL-CAPS lines of <=5 words, no names in quotes. A short quoted title spelled correctly in all 8 benchmark renders.
- Progress bar shows the image model label (`OPENCODE_TG_IMAGE_MODEL_LABEL`) while an image tool is running.
- Usage footer now has a Pictures line: count, render minutes, text-encoder tokens (encoder tokens are added to the input total; counted once per file via `images_seen`). The "est. saved" figure includes those few tokens (negligible).
- Not verified: a real end-to-end photo restyle with a user photo at the new 30-step settings (the live edit cases check routing/tool choice only; only the sloth case actually renders). Headline "#N" ranking for "top 5 news" memes is unreliable (the model does not pick 5 distinct stories reliably); a "search once, choose 5 distinct stories" style tweak was offered, not done.
- Camera snapshot idea was dropped by the owner.

## 3. Other fixes this stretch

- Whole-room / whole-floor light requests: HA GetLiveContext's domain filter hides switches/plugs, so the style text (home_control) and `home_context.py` floor rule say: no domain filter, also look up by name. Latest fix: a switch named like a light ("Bedroom Light", "Study Tubelight") counts as a light; list every match by name including those already in the requested state. Cases: `room-all-lights`, `floor-all-lights` (live), keyed on "Shivi Bedroom Light". They are state-dependent in principle (the switch is currently off); the "already off" wording keeps them valid.
- Bridge: Telegram 429 retry in `tg()`, pictures first, `sendPhotos` retry.

## 4. Decisions waiting on the owner

1. 3090 box (`<user>@<box>`, 24 GB): owner is considering ComfyUI image generation there (expected faster; Q8 21 GB is tight so Q6/fp8 or encoder offload; same model quality ceiling but more control, LoRAs, upscalers; Qwen-Image 2.1 support in ComfyUI NOT verified). Candidate models discussed: Qwen-Image (+Lightning LoRA if one works), Z-Image Turbo, FLUX.1 Krea/Kontext, FLUX.2, Qwen-Image-Edit for restyle. Nothing was run on that machine; ask before any SSH. Integration sketch: image tool calls ComfyUI's HTTP API (workflow JSON, submit, poll, fetch), local sd-cli stays as fallback, ComfyUI LAN-only with a token.
2. Energy data: owner asked about PG&E electric and gas. Options: HA "Opower" integration (login with the owner's PG&E account, daily data, owner adds it in the HA UI so we never hold the password), Green Button manual export, Zigbee meter bridge / Emporia for live electric. Offered, not done: check whether HA already exposes energy entities.
3. Job finder for Hyderabad (phase 1: given a CV, find relevant jobs and the contact details the posting/company publishes; phase 2: scheduled and emailed to an address). Needs from the owner: the CV (Telegram or file path), target role/seniority/salary floor/remote-hybrid, and agreement that contacts are limited to what postings or company pages publish (no scraping personal profiles, no guessed or bulk personal numbers; DPDP Act and spam concerns). Sources found (all unofficial, none vetted): JobSpy MCP (LinkedIn/Indeed/Naukri), Apify India Jobs MCP (Naukri, foundit, Instahyre, Hirist...), Bright Data Naukri MCP, community Naukri/Instahyre/LinkedIn servers. No board offers an official MCP. Fully automated applying risks account bans and breaks site terms, so the plan is search, rank, draft, notify; the owner applies or approves each one.
4. Full live regression suite after the final fixes: run `. scripts/env.sh; node tests/regress.mjs --live` when asked (the image-live-draw case renders ~110 s).
5. Parked from before: llama.cpp b12250 vs b12110 decision, remote DeepSeek takeover issues, HANDOFF section 11 items.

## 5. NEW DIRECTION being designed (not built): autonomous scheduled agents working with RoyVa

Idea: every monitor, scheduled report, watch-and-act rule and research task becomes an independent agent defined by a small spec, run on a schedule, handing results back through RoyVa/Telegram. Phase 2 (email output, schedule) of the job finder is the first use.

Design discussed:
- Agent spec (declarative, reviewable): goal prompt, trigger/schedule, cheap code pre-check (so the model stays idle on quiet days), condition, action level (notify only / safe act / ask-first via the existing Approve/Deny), output target (Telegram now, email later), tool allowlist, limits (time cap, runs/day, token cap).
- Isolation per agent: own OpenCode session per run (never pollutes chat context), own state file (seen-jobs list, last value, last alert time), own log visible via a `/agents` command (last run, result, cost). Agents talk to each other only through notifications/files.
- Shared: GPU scheduling with chat priority (heavy jobs such as image rendering queue behind it; existing one-render lock stays), safety rules (Approve/Deny, quiet hours, dry-run flag, owner-only doors; an agent cannot widen its own permissions), one registry to list/pause/edit/delete agents in chat or files.
- Who builds what: I (the dev assistant) build the generic runner and the MCP tools (job search, contact extraction) once; RoyVa then creates and edits agents from chat as spec files, dry-runs them, and asks the owner to approve before activation. RoyVa does not author new connector code; if that is ever wanted, add a sandboxed "propose a tool" path with review and approval (fits the parked phase 2 learning-module idea).
- Mechanism options: in-gateway asyncio loop (no sudo, simplest, dies with the gateway) vs systemd user timers (robust, but Claude cannot run systemctl; owner would run `install-units.sh`). Leaning in-gateway loop first, HA automations for pure device rules.
- Example agents: morning brief (weather + calendar + mail digest), bedtime check (doors/lights/thermostat), Mustang weekly mileage, unusual power draw or fan left on, mail from specific senders, daily news meme in a GPU-idle window, nightly regression run with a Telegram pass/fail, the Hyderabad job finder.

Alternative being weighed: **NVIDIA NemoClaw** (open-source stack running OpenClaw agents inside the OpenShell sandbox; Landlock/seccomp/network isolation, no access by default; alpha since 2026-03-16; can route to local Ollama/vLLM; docs https://docs.nvidia.com/nemoclaw/0.0.43/index.html, repo https://github.com/NVIDIA/NemoClaw). Whether it has scheduling or a skills system was NOT confirmed. Proposed split: RoyVa stays the front door, router and owner of permissions and exposes its tools (home, mail, image, calendar) to NemoClaw as MCP tools (read-only where possible); simple monitors/reports run on a small RoyVa runner; open-ended agents that may write code (job finder, research) run in NemoClaw's sandbox; all results return through RoyVa to Telegram. Risks: alpha stability, GPU contention with chat, a second agent stack to maintain.

Suggested next steps for the new session:
1. Time-boxed NemoClaw spike (on this machine or the 3090 box): does it run against our local llama.cpp endpoint, does it schedule, can it call RoyVa MCP tools, what GPU/RAM does it use next to the 35B model. Pilot agent: the Hyderabad job finder.
2. Based on the spike, either use it for long-tail agents and build only a small RoyVa runner for monitors, or build the generic runner as designed.
3. Get the CV, target, and contact rule from the owner (section 4, item 3).
4. Optional quick wins still open: headline-picking tweak, real photo restyle test, full live suite, energy entities check.

## 6. How to work in this repo (reminders)

- Run things via `. scripts/env.sh` (node on PATH); gateway tests: `(cd gateway && ./.venv/bin/python -m pytest -q)`; bridge: `node --test bridge/*.test.mjs`; everything: `bash scripts/check.sh`.
- Claude cannot run systemctl or restart services; the owner runs `~/RoyVa/scripts/deploy.sh` (it restarts opencode -> gateway -> bridge and kills in-flight runs, so do not deploy mid-render). Registry changes can be loaded without a restart: `curl -s -X POST localhost:8300/v1/reload`; the MCP processes (e.g. image-gen) only pick up code changes after a deploy.
- Test through Telegram with `node tests/enqueue.mjs "label" "text"` (inject hook) and add cases to `tests/regress_cases.json`; keep fixes generic, not per-prompt (owner feedback).
- Do not make `pgrep -f '<pattern>'` wait loops whose own command line contains the pattern (they match themselves and never exit); use `pgrep -x sd-cli`.
- Past runs can be inspected in `runtime/data/opencode/opencode.db` (table `session_message`, JSON content; use python sqlite3 read-only, the recent rows may still be in `opencode.db-wal`).
