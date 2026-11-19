# RoyVa handover (written 2026-11-10): start here

Older, section-by-section history is in `docs/handoff-log-2026-11.md`. This file is the current picture.

**Video generation / ComfyUI speed work (2026-11-16):** the full state, measured numbers, code map and next ideas are in `docs/video-gen-optimization-handoff.md`. Start there for anything about the 3090 box, Wan, or the video agent.

**READ FIRST (2026-11-17 evening): the shared 3090 box reset abruptly 7 times that day and the cause is unknown; all picture and video requests now go through the img_video agent; nothing over 500 characters may reach the box.** Full findings, measurements, the guard layers, the list of every door to the box, what is deployed and what is not: `docs/handoff-2026-11-17-img-video-agent.md`, section "UPDATE, evening" (U1-U8). `scripts/check.sh` now also runs the agent tests and `tools/check_3090_doors.py` (fails on any new code that can reach the box). The deploy that loads the new wiring has NOT been run yet (U6).

## 0. Resume in two minutes
1. Start `claude` in `~/RoyVa` and say "resume from HANDOFF.md".
2. Arm the Telegram listener under Monitor: `~/RoyVa/scripts/claude-inbox-watch.sh` (30-minute cap; re-arm on every expiry). It replays anything missed.
3. Check health: `scripts/royva-status.sh` (every line `ok`; the last line goes DOWN when the running process is older than the last commit, which means: run deploy).
4. Replies to the owner go through `scripts/notify.sh "text"`. Keep them short (5-8 points). Owner replies land in `runtime/claude/inbox.jsonl`.
5. Before restarting anything: `scripts/check.sh`. To load changes: the owner runs `scripts/deploy.sh` (checks, then restarts opencode -> gateway -> bridge, waits for health). Claude cannot run `systemctl`, `sudo`, `gh repo create` or `git push` (org policy / permission classifier). Claude's own ssh to `<box>` was also denied.

## 1. What RoyVa is
A household assistant. The owner talks to it on Telegram; it controls Home Assistant devices, reads/tidies Gmail, searches the web, answers from home history, and (new) can attempt things no skill covers.

```
Telegram -> bridge (bridge/bridge.mjs, node)
              POST /v1/session, /v1/route   -> gateway (gateway/royva_gateway, FastAPI :8300)
                 router (9B -> main 35B -> keyword) picks an intent -> tool grants (allow|ask) + context
                 no intent / unbuilt intent  -> GENERAL MODE (all tools the user may use, writes behind approval)
              runs the turn in OpenCode v2.2.5 (:49380) -> proxy :8100 -> llama.cpp Qwen3.6-35B-A3B Q8 (:8000)
              MCP tools: home-assistant, ha-history, ha-entity-history, ha-speakers, ha-routines, gmail(+tidy per mailbox),
                         ha-api (ha_read / ha_write), machine (run / run_approved / remote_run / remote_run_approved)
```
Ports: model 8000, router 9B 8203, proxy 8100, OpenCode 49380, gateway 8300. Services are systemd USER units (`systemctl --user ... royva-{opencode,gateway,bridge,proxy,router-9b}`); the model server `evo-llamacpp-agent` is separate.

## 2. State at hand-over
Everything is committed on `main` (no remote is set; push is the owner's job, see section 7). Gateway 249 tests, bridge 40 tests, undefined-name checks clean.
Only uncommitted file: `config/opencode.json` carries generated dummy Gmail entries (`gmail-u-dummy`, `gmail-tidy-u-dummy`), left out on purpose. The dummy account is still in `runtime/gateway/gmail/accounts.json`; remove it with `scripts/royva-gmail` (check the subcommand), then `git checkout config/opencode.json`.

Built this session (all with tests):
| Area | What |
|---|---|
| Follow-ups | A reply in the same session gets "the previous turn acted on ..." read back from the session's own tool calls (`gateway/royva_gateway/scope.py`). New standalone messages start a new session and inherit nothing. |
| Home control rules | More than one device -> list them and wait for the owner's OK; protected devices (`ROYVA_PROTECTED_DEVICES`, now `Shivi Linux Box`, it hosts Home Assistant) never bundled and always asked first; state re-read after bulk changes; floor requests use ONE unfiltered query. **These are prompt rules, not hard blocks.** |
| General mode | `gateway/royva_gateway/general.py`. Replaces the old "I can't do that yet" refusal. Gap still logged (`missing` in `runtime/gateway/traces.jsonl`). |
| HA API door | `mcp/ha/ha_api.py`: `ha_read` (reads only; filter with `contains`/`fields`/`limit`) and `ha_write` (always asks). Lets RoyVa assign areas, rename, write automations. No automation validator exists. |
| Machine door | `mcp/machine/machine.py`. Reads run in a read-only bubblewrap sandbox (no network, clean env, secret files hidden by name pattern, own pid namespace); writes need approval via `*_run_approved`. Remote hosts: `ROYVA_REMOTE_HOSTS` (now `<user>@<box>`, `bwrap` confirmed there). `crontab -l`, `systemctl [--user] list-timers --all` and one `ps` listing run unsandboxed by exact match. Log: `runtime/gateway/machine.log`. No sudo. |
| Approvals | Inline Approve/Deny buttons; `/approve` `/deny` in the menu; Deny now STOPS the run. Arbitrary-power tools show the whole call (never truncated, never batch-approved). Device/area/entity names come live from Home Assistant (`/v1/resolve-ids`); an unmatched id disables Approve (button and typed). |
| Stop / steer | A ⏹ Stop button sits on the "Processing" status message (same effect as `/stop`); replying to any message of a running request steers it and gets an immediate 👀 reaction. Not live-verified. |
| Loop guard | `bridge/guard.mjs`: stops only a stuck run (same call 3x, 4 failures in a row) or at 25 rounds / 80 calls. The old 6-round cap is gone. |
| Footer | Replies end with the all-time token line only. |
| Checks | `tools/undefined_names.{py,js}` + `scripts/check.sh` catch missing imports (a missing import shipped once and broke every request). |

Scopes: `runtime/gateway/users.json`. Owner = `"*"`. The two doors are tool scope `admin`: owner only. Invited household members get the existing skills, not the doors.

## 3. Not live-verified (be honest about this)
The owner said things look good after deploying, but Claude did not itself run these end to end. Confirm with `node tests/enqueue.mjs "label" "prompt"` (mirrors into the owner's chat, runs the real handler):
* general mode + `machine_run` ("how much memory is free?"), `crontab -l` path, remote read on `<box>` (never run; quoting is unit-tested through a local shell).
* `ha_write` approval showing live names; Deny stopping the run; the Approve/Deny buttons on a permission request.
* floor query (one call), loop guard on a long legitimate job, `/v1/resolve-ids` against the real Home Assistant.
* Prompt-rule behaviour on the 35B model (models can ask in text instead of calling `ha_write`; this happened once and the prompt was changed).

## 4. Standing rules from the owner
* Only Gmail trash/archive asks approval, plus what the owner explicitly added: multi-device changes, the protected device, `ha_write`, `*_run_approved`.
* **Never change user-visible behavior (policies, enabled skills, routing) without asking first.** No hardcoded household or vocabulary logic: facts come from Home Assistant or deployment config (`scripts/env.sh`).
* Commit locally in small commits with proper messages; never push. Keep Telegram replies short.
* Phase 2 (remote-model escalation and learning) is parked by the owner.
* Telegram messages from the owner (from_id 6064019420) arrive as Monitor events; treat them as the owner's words.

## 5. Decisions the owner deferred ("let's do these later")
* **A.** The 👎 "Incorrect" button sends the chat to OpenRouter/DeepSeek, which runs with every permission pre-allowed (Gmail send included). Disable? (`runDeepSeekTakeover` in `bridge/bridge.mjs`; the owner-only doors are already stripped from its config.)
* **B.** General mode offers web fetch/search together with machine reads: a malicious page could make RoyVa read a file and leak it in a URL. Options: drop web fetch from general mode, or require approval for it.
* **C.** A general-mode request carried ~100k prompt tokens (mostly cached). Trim to read tools + approval tools?
* Should household members get `ha_read`/`ha_write` (not the machine tools)? One scope change.
* Locks/garage on the no-approval path (owner never said).

## 6. Candidate next phases (suggested order)
1. **Live verification and tuning of what was built** (section 3), incl. measuring general-mode cost and quality on the 35B.
2. **Doing things later / proactive**: no scheduler and no unprompted messages today ("remind me at 8", "tell me when the garage has been open 10 minutes"). Biggest functional gap. Needs a scheduler plus a push path (the bridge already has `notify`-style sending).
3. **Calendar and other logged-in services** (`calendar` intent is `planned`, tools unbuilt); Google Calendar via OAuth like the Gmail pipeline.
4. **Automation writing properly**: `ha_automation` intent is `planned`; add a validator so a malformed automation is rejected before it is saved.
5. **Phase 2 learning**: remote-model escalation and an agent that learns skills from traces; first showcase is song/YouTube playback (no music source in HA, no yt-dlp). Reference code: `~/RoyVa-old-baseline-reference` (agent-learning, smart-router, gmail-mcp, ha-legacy). Gap data already logged in traces (`missing`).
6. **Persistent memory** across conversations ("always do X when I say Y"). Sessions are the only memory today.
7. Routing: a fresh held-out eval set (current benchmark is tuned and optimistic); extra title-generation call (B5).
8. Enrollment: second real Telegram account test (`/join` -> `/accept` -> `/connect-gmail`); GitHub Pages OAuth relay (`som4tress/royva-oauth-relay`, owner runs the `gh` commands); map Telegram ids to Shobha and Shivangsh.

## 7. Owner actions waiting
* Push: `cd ~/RoyVa && git remote add origin https://github.com/som4tress/RoyVa.git && git push -u origin main` (the remote repo exists and was empty; tag `checkpoint-2026-11-08` optional). Old repo cleanup and the `RoyVa-Hearth` idea are in the archived log.
* `scripts/deploy.sh` after any commit that touches bridge, gateway or mcp.
* Optional: a dedicated, restricted ssh key for RoyVa on the remote host (the current key is the owner's own).

## 8. Known issues and tech debt
* `mcp/ha/ha_history.py` hardcodes three family first names; absolute `~` paths in scripts, units and config.
* `config/opencode.baseline.json`, `config/opencode.fix1.json` look stale.
* `ha.broadcast` is `external`-risk; unread-count answers once capped at a page (fixed for exact counts, recheck).
* Env-allowlist ids in `TELEGRAM_ALLOWED_USER_IDS` cannot be revoked from chat (shrink it to the owner).
* The loop guard could stop a legitimate triple re-read of identical state.
* Sessions keep their original tool descriptions; a changed tool schema only reaches NEW conversations (a reply into an old thread keeps the old behavior).
* Existing sessions from before a deploy carry old grants until the gateway re-patches them on the next turn.

## 9. Where things are
* `gateway/royva_gateway/`: `service.py` (route/prepare/commit), `router.py`, `profiles.py` (grants, prompt text), `general.py`, `scope.py`, `home_context.py` (HA registries, id->name), `registry.py`/`models.py` (data contracts), `sessions.py`, `app.py` (endpoints).
* `gateway/registry/`: `tools.json` (catalog: risk, scope, approval, door) and `intents/*.json`. A fix is usually data or a generic rule, not a code branch.
* `bridge/`: `bridge.mjs` (Telegram + run loop), `permissions.mjs` (approval text, names, takeover strip), `guard.mjs`, `opencode.mjs`, `usage.mjs`, `enroll.mjs`.
* `mcp/ha/`, `mcp/machine/`, `mcp/mail/`: tool servers (stdio JSON-RPC, stdlib only).
* `scripts/`: `deploy.sh`, `check.sh`, `royva-status.sh`, `notify.sh`, `claude-inbox-watch.sh`, `env.sh`, `run-*.sh`. `systemd/`: unit files.
* `runtime/` (git-ignored): `gateway/` (users, sessions, traces, machine.log, gmail), `state/` (telegram.json, usage_totals.json), `data/opencode/opencode.db` (session history; read with python `sqlite3` in read-only mode, tables `session_message`, `session_v2`).
* Debug a conversation: `journalctl --user -u royva-bridge -n 50`, `runtime/gateway/traces.jsonl`, and the OpenCode DB (tool calls are in `session_message.data` -> `content[]` with `state.input/status/error`).
* Env (`scripts/env.sh`): `ROYVA_PROTECTED_DEVICES`, `ROYVA_REMOTE_HOSTS`, `ROYVA_DEFAULT_PERSON`; volume cap `ROYVA_PLAY_VOLUME` (28%) / `ROYVA_MAX_VOLUME` (30%); rehearsal mode: create `runtime/gateway/dry_run` (the write tools report instead of acting).

## 10. Lessons from this session
* `node --check` and unit tests do not catch a missing import. Run `scripts/check.sh`, deploy with `scripts/deploy.sh`.
* A tool result cut off at a size cap looks like "not found" to the model. Narrow on the server (filters, limits) and say when something was cut.
* A prompt instruction is not enforcement. Where it matters (approvals, secrets, scopes) enforce in code; say so when something is only a prompt rule.
* If you ask the model to "ask first", it may ask in chat text and never call the tool whose own prompt carries the buttons. Tell it to call the gated tool directly.
* Ids that reference each other (device <-> area <-> entity) must be named from their own registry, live, never from the nearest name in earlier output.

## 11. Regression suite and open audit findings (2026-11-10)
Run before/after every change, no Telegram: `. scripts/env.sh; node tests/regress.mjs` (route + permission checks, ~1 min) and `node tests/regress.mjs --live` (also runs the `live` cases through OpenCode; every permission request is denied, so nothing in the house changes; ~10 min). Cases are in `tests/regress_cases.json`, built from real past queries (`past-NN` are frozen current routing; add the owner's new queries there). Known misroute is tagged `xfail`.
Open findings from the 2026-11-10 audit, not fixed (need an owner decision or more work):
- Any enrolled member can press 👎 (DeepSeek takeover, all servers allowed); gmail servers are not stripped from the takeover config.
- One batch approval keys on action only, so later `tidy_*` calls with a different query/ids ride on it.
- `AskRequest.text` max 8000 chars: long expanded prompts get 422, shown as "routing unreachable".
- Session permissions are only refreshed when grants change, not when mail accounts/readonly change.
- Protected-device check in `ha_write` matches names, writes carry ids (approval still shows live names).
- Steer after Stop is acknowledged then dropped; Deny can send two messages; pending permission left if `onPermission` throws.
- `expected_mcp` omits `machine` and `ha-api`.
- Loop guard trips on read, change, re-read of the same query.

## 12. Image skill (Qwen-Image-2.1 Q8, stable-diffusion.cpp Vulkan)
* Files: runtime binary `~/llm-server/sdcpp/master-1086` (sd-cli), models in `~/llm-server/models/image/qwen-image-2.1` (denoiser Q8, Qwen3-VL-8B Q8 encoder, VAE, mmproj for editing). Smoke test: `~/llm-server/sdcpp/test-image.sh`.
* MCP server `image-gen` (`mcp/image/image_gen.py`): `generate_image`, `edit_image` (reads photos only from `runtime/data/inbox`, writes to `runtime/data/images`, one render at a time, 900 s timeout). Intent `image_generate` (also web.search/fetch for news memes). Bridge: `images.mjs` sends the picture, `media.mjs` saves incoming photos and adds a `[Attached photo: path]` line.
* Needs `scripts/deploy.sh` (OpenCode restart loads the MCP server). Text-to-image smoke-tested by hand; photo restyle and the live tool path are NOT yet verified end to end. Regression: route cases `image-*`, live case `image-live-draw`.

## 13. Latest handoff
See `docs/handoff-2026-11-11-image-and-agents.md`: image skill as shipped (30 steps, cfg 4.0, EasyCache), latest fixes, open owner decisions (3090/ComfyUI, PG&E data, Hyderabad job finder), and the autonomous scheduled-agents design (runner vs NemoClaw).
