# RoyVa dev handoff (written before moving the session into tmux)

## Restart the dev stack (each is a long-running process; start in this order)
    scripts/run-proxy.sh        # logging proxy :8100 -> llama :8000   (captures in captures/)
    scripts/run-opencode.sh     # isolated vanilla OpenCode :49380
    ROYVA_INJECT_DIR=$PWD/runtime/inject scripts/run-bridge.sh   # Telegram bridge (@roy_has_bot); prod unit opencode-telegram-vanilla must be stopped
    scripts/run-router-model.sh emb Qwen3-Embedding-0.6B-Q8_0.gguf 8201
    scripts/run-router-model.sh llm Qwen3-4B-Instruct-2507-Q8_0.gguf 8202
    scripts/run-router-model.sh llm Qwen3.5-9B-Q8_0.gguf 8203      # if download finished (models/router/)
Model server for Qwen 35B (port 8000) is the systemd unit evo-llamacpp-agent (now Q8_0, launch_qwen36.py).
Telegram <-> Claude: scripts/notify.sh "text" sends a message; replies (to it, or "cc: ...") land in runtime/claude/inbox.jsonl.
Units (not installed): systemd/royva-*.service + scripts/install-units.sh.

## Findings so far
- BF16 -> Q8_0 for the 35B: decode 8.5 -> ~50 tok/s, PP 150-480 -> 1,100-1,700 tok/s.
- Replay experiment (tests/replay.py, 600 reqs): OpenCode's coding prompt + 12 coding tools cause refusals / no-tool answers
  (P2 55%, P3 10% first-tool-ok); short prompt + only relevant tools + capability sentence -> 100%. Prefix cache not a confounder.
- OpenCode input is deterministic post-MCP; variation = model sampling. Decision: stay with OpenCode, fix via config.
- Bugs B1-B7 in BUGS.md (coding prompt, FS exploration, cold-start MCP tool race, area/floor thrash, title call, runaway loop, refusals).
- Staged but NOT applied: config/opencode.fix1.json (royva agent: own system prompt, deny * + allow list, default_agent).

## Gateway (gateway/, python venv .venv, 22 tests pass: .venv/bin/python -m pytest)
- royva_gateway/models.py (contracts+schemas), registry.py (validated loader), classifiers.py, registry/tools.json (41 tools),
  registry/intents/*.json (9 seeds), eval/eval_set.jsonl (118 items, leak-checked), bench/run_bench.py, bench/emb_sweep.py.
- Benchmark (test split, 58 items): rules 72% macro; embedding(Qwen3-Emb-0.6B, with instruction prefix) 65%; 4B LLM 81% (p50 358 ms).
- Embedding sanity sweep: instruction prefix HURTS (70% with, 87% without top-1 on standalone). EOS suffix hurts too. => set use_prefix=False.
- Next: rerun embedding without prefix; add 9B; try hybrid (embedding confident -> use it, else LLM); few-shot prompt for LLM; cross-domain is weak (~40%).

## Open items
- Decisions from user: gateway = separate service (decided), small model preferred over Qwen35B (decided), intents list (decided).
- Do not commit/push anything unless the user asks.

## Update 2026-11-08
- Router decision: Qwen3.5-9B Q8 + few-shot is the default router model (user OK with ~0.5 s); 4B Q8 kept as fast fallback. Embedding stage dropped for v1.
- Gateway design: ONE base OpenCode agent `royva` (deny *, short system prompt) + per-session `permissions` (PATCH to widen). See BUGS.md.
- Readiness: GET /api/mcp (Basic auth opencode:$OPENCODE_SERVER_PASSWORD) lists MCP servers with status; wait for all `connected` (fixes B3).
- Telegram: user is travelling; use scripts/notify.sh, replies land in runtime/claude/inbox.jsonl.
- New intents added: routine_trigger, web_lookup research phrasing (steps 10), grouped status in home_state. real_v1 eval set is now a TUNING set; need fresh held-out messages.

## Update 2026-11-08 (later)
- Gateway service built (gateway/royva_gateway: service.py prepare/ask/route_for_bridge, router.py, runner.py round-guard, profiles.py, home_context.py, app.py).
  Endpoints: POST /v1/ask (self-contained), POST /v1/session + POST /v1/route (bridge path), GET /healthz, POST /v1/reload. Port 8300. 42 tests pass.
- Bridge uses the gateway when ROYVA_GATEWAY_URL is set (default in scripts/run-bridge.sh). Round guard is enforced in the bridge's onProgress.
- Base agent `royva` denies everything; a request that bypasses the gateway gets NO tools (caused a bad reply to a real user message during a restart).
- ha-history MCP (mcp/ha/ha_history.py + vendored ha_* helpers) is wired: get_visited_locations (home_history, active), get_on_entities_with_context and
  get_device_status_report (home_state). Known gaps: Ford distance (no generic entity-history tool yet), camera events, TTS, synced speakers, run-routine.
- Start order: llama -> proxy -> opencode -> gateway -> bridge (units in systemd/, not installed; scripts/install-units.sh).
- Approved by user: travel-aware location (use phone location via HA when away); concise grouped status.

## Update 2026-11-08 (end of hardening pass; user away)
- Gateway README: gateway/README.md (architecture, safety model, failure table, API, how to extend, runbook). 99 tests: `cd gateway && .venv/bin/python -m pytest`.
- Safety model: read tools allow; write/external tools `ask` (bridge /approve) unless intent `auto`; read_only intents never get write tools. No write intent is active.
- Router: chain 9B+fs -> 4B+fs -> rules (breaker 2 failures / 30 s); fail closed when none can route. Router models are separate llama-servers on 8203 / 8202.
- Context is generated from HA (home map, location, household, speakers); per-turn `current_location` when the user is away (city only; never the street address).
- Escalation/learning (phase 2) is parked by the user. `/v1/stats` already counts unsupported requests (`unsupported_demand`) as the demand signal.
- Stack started by me from this session (dies with it): proxy 8100, OpenCode 49380, gateway 8300, bridge, router models 8202/8203. llama 8000 is the user's systemd unit.
- Telegram: scripts/notify.sh to message the user; replies (reply to it or `cc:`) land in runtime/claude/inbox.jsonl.
- Do not commit or push unless the user asks.

## Update 2026-11-08 (options 1 + 2 live)
- LIVE (no dry run): routine_trigger ("Goodnight" -> automation "Good Night", allowlist = ["Good Night"]) and media_playback (speak/TTS, radio streams, synced Sonos
  grouping, volume/control). Verified: dry-run flows for every example, then one harmless LIVE write (pause an idle speaker) with the "What I did" footer.
- Privacy: private chats only; email scope owner-only and SILENT for others; home_actions scope owner-only (polite refusal). users.json holds the owner only; 2 IDs are
  on the bot allowlist. `_policy.silent_scopes = ["email"]`.
- Telegram with Claude: /claude (sticky) /royva, cc:/claude:/@claude, replies to Claude's messages. Heartbeat-based ack. Listener: scripts/claude-inbox-watch.sh (replays unread;
  re-arm each Monitor expiry). Injected tests use `as: 'royva'`. ANY question for the user goes to Telegram (scripts/notify.sh).
- Stack now runs under scripts/supervise.sh (bridge, gateway, OpenCode). Router models 8202/8203 run unsupervised (systemd units exist, not installed).
- Open questions sent to the user (Telegram msg 12287): KBAY stream URL/presets, allow Good Morning/Home Away, silence for other refusals, which ID is whom.
- Known hardcode left: vendored mcp/ha/ha_history.py has the 3 family names in its `person` enum (generalize from HA person entities).

## Update 2026-11-08 (owner's answers to the numbered questions)
- KBAY: the user's URL was the station website; the real stream (found in the station's player config) is saved as radio presets "KBAY" and "Bay Country"
  (MP3 https://live.amperwave.net/direct/alphacorporate-kbayfmmp3-ibc4; AAC twin exists). Presets live in runtime/gateway/radio_presets.json.
- Routines allowlist = Good Night, Good Morning, Home Away ("allow all" read as the three routine automations; the other ~19 automations are event automations and stay off).
- House actions (speakers, routines) are open to everyone on the bot; ONLY email is partitioned (owner only, silent for others). home_actions scope removed.
- Which Telegram ID is whom: deferred by the user (they will set up Shobha's and Shivangsh's email later).
