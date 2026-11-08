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
* `mcp/ha/ha_history.py` still hardcodes three family first names; absolute `/home/somdutta` paths in scripts/units/config.
* Fresh held-out routing eval set needed (current benchmark is tuned, optimistic). B5 (title-generation extra call) open.
* Map Telegram IDs to Shobha and Shivangsh (email scope) later. Planned/off: calendar, trackers, HA automation writing, camera analysis, home_control.
* Phase 2 (remote-model escalation + learning) is parked by the user.
