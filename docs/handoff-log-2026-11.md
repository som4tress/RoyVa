# RoyVa handoff (2026-11-08)

## Do this first (you, in a normal terminal, after exiting Claude)
```
~/RoyVa/scripts/install-units.sh       # enables + starts the whole stack at boot, disables the OLD Telegram bridge
~/RoyVa/scripts/royva-status.sh        # every line should say "ok"
cd ~/RoyVa && gh repo create som4tress/RoyVa-Hearth --private --source . --push     # first push (no remote is set on purpose)
```
Then (optional proof) reboot, wait ~3 min, run `royva-status.sh` again. Delete the OLD GitHub repo `som4tress/RoyVa` yourself
(a read-only copy is in `~/RoyVa-old-baseline-reference`, useful for phase 2: agent-learning, smart-router, gmail-mcp, ha-legacy).
In Telegram send `/royva` once so plain messages go to RoyVa (`/claude` or `cc:` talks to Claude).

## State
* Git: branch `main`, tag `checkpoint-2026-11-08`, clean tree, no remote. `gateway/eval/real_v1.jsonl` (real messages) is git-ignored.
* Served models: main Qwen3.6-35B-A3B Q8 (:8000, systemd `evo-llamacpp-agent`, not restartable by Claude), router Qwen3.5-9B Q8 (:8203, 2 slots x 4096). Fallback router = main model via proxy :8100.
* Stack: proxy :8100 -> OpenCode v2.2.5 :49380 -> gateway :8300 -> Telegram bridge. Units in `systemd/`, dev supervision via `scripts/supervise.sh`.
* Volume cap: 28% default, 30% ceiling (`ROYVA_PLAY_VOLUME`, `ROYVA_MAX_VOLUME`). Rehearsal mode: create `runtime/gateway/dry_run`.
* Token totals: `runtime/state/usage_totals.json` (shown in every reply footer).
* Photos work; videos are expanded to <=8 frames by the bridge (OpenCode media plugin is not loaded).

## Resuming Claude
Start `claude` in `~/RoyVa`, say "resume from HANDOFF.md". Then re-arm the Telegram listener under Monitor:
`~/RoyVa/scripts/claude-inbox-watch.sh` (30-minute cap, re-arm on expiry). Standing rule: replies to Telegram messages go back through
`scripts/notify.sh`. Claude cannot run `systemctl`, `sudo`, or `gh repo create/git push` (org policy / permission classifier): the user runs those.

## Open items
* Music/YouTube playback: no music source in HA (no media_extractor/Spotify/Plex/Music Assistant, no yt-dlp). Parked as the phase-2 learning-module showcase.
* "All speakers" skips the AirPlay Office Den (cannot be grouped): plan is to play on it separately and say it is not in sync.
* `mcp/ha/ha_history.py` still hardcodes three family first names; absolute `~` paths in scripts/units/config.
* Fresh held-out routing eval set needed (current benchmark is tuned, optimistic). B5 (title-generation extra call) open.
* Map Telegram IDs to Shobha and Shivangsh (email scope) later. Planned/off: calendar, trackers, HA automation writing, camera analysis, home_control.
* Phase 2 (remote-model escalation + learning) is parked by the user.


## Gmail pipeline + Telegram enrollment (2026-11-08, built while the user was away; all UNCOMMITTED unless noted)
* Done and tested (gateway 216, bridge 30 tests): `gateway/royva_gateway/{gmail_enroll,gmail_cli,directory}.py`, per-person MCP wiring (profiles/service: `gmail-u-<name>`),
  scope renamed email -> gmail, endpoints `/v1/enroll/*` and `/v1/admin/restart-opencode`, bridge `enroll.mjs` + hooks in `bridge.mjs`, relay page `docs/oauth-relay/`, `scripts/royva-gmail`.
* Live-verified: dummy Gmail connected via paste-back (then removed); isolation; unknown-mailbox message; owner-only invite on the live store with a fake id.
* NOT verified end to end: a real second Telegram account doing /join -> /accept -> /connect-gmail (needs a second account); restart-when-idle after a real connect; the Web-client + GitHub Pages route
  (needs the user: public repo `som4tress/royva-oauth-relay` + Pages [repo create was denied by the classifier; the local repo ~/royva-oauth-relay is committed], Google Web client JSON at ~/.royva/gmail-client.json).
* Known gaps: unread-count answers are wrong (model reports a capped page, e.g. 201 vs ~7.6k); env allowlist ids in TELEGRAM_ALLOWED_USER_IDS cannot be revoked from chat (shrink it to the owner).
* Backups of the bridge before each change: runtime/bridge.mjs.pre-*.bak.

## Session handoff 2026-11-09 (read this first)

**Goal (owner's words, restated):** RoyVa should be an *autonomous*, generic assistant. When no skill matches, it must judge and attempt on its own (consult itself on possible paths), not answer "I can't". Example that failed: "find this cron job on the machine you run on / ssh somewhere" and "how much memory is free?" got zero tools and a guess. Design under discussion (NOT built, owner has not approved): fallback with read-only tools (B) vs. model picks tools from the whole skill catalog within scopes (C) vs. a sandboxed machine-access capability. The owner wants autonomy; clarify with them which level (including machine shell/ssh) before building.

**Standing rules from the owner:** only Gmail trash/archive asks for approval; everything else (device control, media, routines) runs unattended. Never change user-visible behavior (policies, enabled skills, routing) without asking first. No hardcoded household/vocabulary logic. Commit locally in small commits; do not push. Tell the owner via Telegram (`scripts/notify.sh`); keep replies short (5-8 points). Re-arm `scripts/claude-inbox-watch.sh` under Monitor (30 min cap). Owner's chat is sticky in /claude mode until they send /royva (a reply to a RoyVa message now goes to RoyVa).

**Done this session (all committed, 219 gateway tests, 30 bridge tests):** Gmail enrollment + per-person isolation + Telegram invite flow, exact unread counts, local-time (not UTC) in HA history/device/context tools, doorbell false-event fix, home_control enabled with no approval + look-up-first style, lights wired as switches returned for the model to judge (no keyword list), policy-pin test, original on/off tool descriptions restored after an audit against 49b1d97 (HA status output identical old vs new for default/floor/area/name queries).

**Known open:** GitHub Pages OAuth relay (owner runs two `gh` commands), second real Telegram account for an enrollment test, locks/garage on the no-approval path (owner has not said), fallback autonomy (above), `config/opencode.json` carries generated dummy Gmail server entries (uncommitted on purpose).

## Session 2026-11-09 (later): autonomy + approvals (all committed, 243 gateway / 31 bridge tests; NOT yet restarted or live-tested)
* Follow-ups inherit the previous turn's tool-call scope (`gateway/royva_gateway/scope.py`). Home control: approval before multi-device changes, protected devices (`ROYVA_PROTECTED_DEVICES` in `scripts/env.sh`) never bundled, state re-read after bulk changes. These are prompt rules, not hard blocks.
* Bridge: Approve/Deny inline buttons under permission requests; `/approve` `/deny` in the command menu. Arbitrary-power tools show the whole call and are never batch-approved (`FULL_CALL` in `bridge/permissions.mjs`).
* General mode (`general.py`): no matching intent, or a matched intent that is unbuilt, runs with every tool the user may use (writes behind approval) instead of refusing; the gap is still logged (`missing` in traces).
* Doors, owner-scoped (tool `scope: admin`, `approval: true` on the write side): `mcp/ha/ha_api.py` (ha_read / ha_write) and `mcp/machine/machine.py` (run / run_approved / remote_run / remote_run_approved). Read vs write on machines is enforced by a read-only bubblewrap sandbox (no net, clean env, secrets hidden), not by a command list. `ROYVA_REMOTE_HOSTS` (env.sh) is the ssh allowlist. Commands are logged to `runtime/gateway/machine.log`.
* To load: restart `royva-opencode`, `royva-gateway`, `royva-bridge` (user units; Claude cannot). New servers are NOT in `expected_mcp` on purpose.
* Not verified: any live turn; remote ssh (Claude's ssh was denied, quoting is unit-tested through a local shell); `crontab -l` and `ps` run unsandboxed via a tiny exact-match list. Step "request_tools meta-tool" deliberately not built (no mid-run grant path known).
* `config/opencode.json` still carries the uncommitted dummy Gmail entries; the ha-api and machine entries are committed.

## Audit 2026-11-10 (owner asked; all fixes committed)
* Bug I shipped: `bridge.mjs` used `loopVerdict` without importing it, so every request failed with ReferenceError until the bridge was restarted with the fix. `node --check` and unit tests do not catch missing names: run `scripts/check.sh` (undefined-name checks for py and js via `tools/`, plus all tests) before restarting anything.
* Fixed: the remote DeepSeek takeover (👎 "Incorrect" button, runs with every permission pre-allowed) was handed the live config, which now includes the `machine` and `ha-api` servers; `withoutOwnerDoors()` strips them. Sandbox secret hiding is now by file-name pattern (it missed opencode.env, connection.env, runtime.env, the Google client_secret json).
* Open, need the owner's decision: (1) the 👎 button still sends the conversation to OpenRouter/DeepSeek with all permissions allowed (incl. Gmail send); (2) general mode offers web fetch/search together with machine reads: prompt injection could read a file and send it out in a URL; (3) general-mode requests carry ~100k prompt tokens; (4) stale `config/opencode.baseline.json` / `opencode.fix1.json`; (5) `mcp/ha/ha_history.py` hardcodes household names; absolute `~` paths everywhere.

## Local-flow hardening 2026-11-10
* `scripts/deploy.sh` = check.sh, then restart opencode -> gateway -> bridge in order, then wait for `royva-status.sh` to be healthy. Use it instead of restarting by hand.
* `royva-status.sh` now also checks: ha-api and machine MCP connected, bwrap works, and that the RUNNING build is not older than the last commit touching bridge/gateway/mcp (a stale process is reported DOWN).
* Machine door fails closed when bwrap/ssh is missing; Home Assistant refusals now carry HA's own message; request failures log the stack to the journal.
* Smoke tests of the local flow without typing in Telegram: `node tests/enqueue.mjs "label" "prompt"` (mirrored into the owner's chat, run through the real handler).
