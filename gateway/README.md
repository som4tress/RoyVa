# RoyVa gateway

Sits between a front end (the Telegram bridge) and OpenCode. For each message it decides **what kind of request it is** (an *intent*),
grants the conversation **only the tools that intent needs**, adds a little generated context, and lets OpenCode do the work.
Measured effect: the first model step shrank from ~5.8k to ~0.7k tokens and the "I can't do that" refusals went away.

## Principles
* **Generic, never per-prompt.** Nothing branches on prompt text. Household facts (floors, areas, people, speakers, location) are *generated
  from Home Assistant*; deployment values live in `scripts/env.sh`. `tests/test_gateway.py::test_code_contains_no_household_specific_terms` enforces it.
* **Intents and tools are data** (`registry/`), validated on load. A fix is a new generic tool, a general rule in an intent, or a registry example.
* **Fail closed.** If routing is impossible the user gets a clear message; a model with no tools never improvises an answer.
* **Least privilege.** Tools are granted per conversation and widen only when a new intent appears (union, recomputed each turn).

## Request flow
```
Telegram ─► bridge ─► POST /v1/session (base agent, no tools)
                  └─► POST /v1/route   {text, session_id, is_reply}
                         router chain: 9B ─► main 35B (already loaded, no extra VRAM) ─► keyword rules      (circuit breaker per classifier)
                         intents ─► grants (allow|ask) ─► PATCH OpenCode session permissions
                         returns {kind: run|answer|error, prompt, cap, ...}
                  └─► bridge runs the turn itself (progress, steer, /approve), enforcing the round cap
```
`POST /v1/ask` does route + run in one call (used by tests and simple clients).

## Safety model
| tool risk | intent `write_policy` | OpenCode effect |
|---|---|---|
| read | any | `allow` |
| write / external | `read_only` | refused (also rejected at registry load) |
| write | `confirm` | `ask` → bridge shows `/approve` or `/deny` |
| write | `auto` | `allow` (never for `external` tools: rejected at load) |

* `skill, shell, edit, write, read, glob, grep, subagent, execute, question` are always denied (`Settings.never_grant`).
* Agent-authored intents can't become active with write tools without `approved_by` (registry validation).
* The base agent (`config/opencode.json › agents.royva`) denies everything and treats tool/email/web text as data, not instructions.
* Per-turn **round cap** (intent `steps`): a runaway loop is interrupted and the model is told to wrap up. A round is one model step; parallel calls inside one round are fine.

## Failure behaviour
| Failure | Result |
|---|---|
| primary router model down / slow / malformed reply | next classifier; breaker opens after 2 failures for 30 s |
| every classifier down | clear "routing unavailable" reply, no session, no tools |
| keyword fallback finds nothing | treated as *unavailable*, not as "no intent" |
| OpenCode error while preparing or running | clear error reply; session never left `busy`; trace `outcome=error` |
| gateway not ready (MCP not connected) | HTTP 503; bridge says it is starting up |
| gateway down | bridge says routing is unreachable (no silent failure) |
| invalid registry edit on reload | HTTP 400 with the problems; the running registry is kept |
| capability not built (planned tool) | direct honest reply; demand recorded in `/v1/stats › unsupported_demand` |

## API (localhost only; optional `ROYVA_GATEWAY_TOKEN` bearer token on `/v1/*`)
`GET /healthz` (open) · `GET /v1/registry` · `GET /v1/stats` · `POST /v1/ask` · `POST /v1/session` · `POST /v1/route` · `POST /v1/reload`
Pinned by `tests/test_app.py::test_route_table_is_exactly_the_documented_api`.

## Extending
* **New tool:** add it to `registry/tools.json` (`risk`, `available`), connect its MCP server in `config/opencode.json`, add the server to
  `Settings.expected_mcp`.
* **New intent:** one file in `registry/intents/` (examples, negatives, continuations, profile). Cross-intent and "no intent" few-shot
  examples go in `registry/router_examples.json`. Then `POST /v1/reload`.
* **Planned capability:** mark its tools `available: false` and the intent `planned`; users get an honest reply and the demand is counted.

## Runbook
Start order: llama (8000) → proxy (8100) → OpenCode (49380) → gateway (8300) → bridge. Router model: 9B (8203); fallback is the main model via the proxy (8100).
`scripts/run-*.sh`; units in `systemd/` (installed with `scripts/install-units.sh`). Tests: `.venv/bin/python -m pytest`.
Traces: `runtime/gateway/traces.jsonl` (rotates at 20 MB, keeps 3). Sessions: `runtime/gateway/sessions.json` (pruned at start: 30 days / 5000).
Debug a bad answer: find its `trace_id` in `traces.jsonl` → `capture_ids`/proxy captures show exactly what the model received.

## Privacy and who may do what (added 2026-11-08)
* **Private chats only.** The bridge ignores group chats completely (no reply, no processing), for RoyVa and for Claude.
* **Per-user scopes** (`runtime/gateway/users.json`, deployment config, not code): `{"telegram:<id>": {"person": "...", "scopes": ["*"]}, "_policy": {"silent_scopes": ["email"]}}`.
  Intents may carry a `scope`; today only `email` (on mail_read) is scoped. Per the owner, anyone on the bot's allowlist may run routines and drive speakers. A user without a required scope gets nothing run and either a short
  refusal or, for scopes listed in `silent_scopes` (email), **no reply at all**. Unlisted users have no private scopes. Grant = add the scope to that user's list.
* A user can't borrow another user's tools: grants are recomputed per turn from the intents the *current* user may use.

## Acting on the house (options 1 and 2)
* `mcp/ha/ha_routines.py`: `list_routines`, `run_routine`. Only routines in `runtime/gateway/routines_allowlist.json` can run (now Good Night, Good Morning, Home Away; the other automations stay off; empty file = none).
* `mcp/ha/ha_speakers.py`: `list_speakers`, `find_radio_stream` (public Radio Browser + owner presets in `runtime/gateway/radio_presets.json`), `speak` (HA `tts.speak`),
  `play_stream` (optionally `synced`: Sonos grouped under a leader; others play separately and the result says so), `group_speakers`, `control`.
  Speakers are discovered from HA (TVs excluded); targets by friendly name or `all`; unavailable speakers are skipped and reported.
* Policy is `auto` (no approval prompts, as the owner chose). Instead every reply ends with **"What I did"**, built by the bridge from the tool calls OpenCode actually
  recorded (ground truth, not the model's words); a turn that could act but did nothing says "No action was taken".
* `ROYVA_DRY_RUN=1` in an MCP server's `environment` (config/opencode.json) makes its writes report what they WOULD do. Remove it for live.
* Multi-intent requests (e.g. fetch news then speak it) get an instruction to complete every part and deliver as asked, not only reply in text.

## Running it
`scripts/supervise.sh <name> <cmd>` restarts a command whenever it exits (dev stand-in for systemd). For a persistent stack install the units once:
`! ~/RoyVa/scripts/install-units.sh` then `! systemctl --user start royva.target` (units now include both router models).

## Known gaps (by design, next phases)
Remote-model escalation and recipe learning (phase 2); write capabilities (speakers/TTS, run-routine, automations, calendar, trackers) are
registered as `planned` and stay off until a human approves them; per-user mapping beyond `ROYVA_DEFAULT_PERSON`.
