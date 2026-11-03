---
name: Speak On Host
description: Make the master host (Shivangsh's somdutta-linux box) say something out loud via espeak-ng + PipeWire, and fix "I heard nothing" fast. Use for any "say X on Shivangsh's speaker / computer / host" request.
---

# Speak on the master host

Speak text out loud on `somdutta-linux` (same box this session runs on).
No Home Assistant, no Sonos, no TTS proxy — local `espeak-ng` → `paplay`.

## Workflow

1. One command:

   ```sh
   SSHPASS='<password>' ~/.config/opencode/skills/speak-on-host/scripts/say-on-host.sh "Hello Shivangsh"
   ```

   Preview without playing: add `--dry-run`.
   Different machine/sink: `SAY_HOST=... SAY_SINK=...`.

2. Confirm from the output: it prints `spoke: <text>`. Then, and only then,
   check the sink was **RUNNING** during playback.
3. If the user says they heard nothing, run the diagnosis in Gotchas below —
   do not start by doubting SSH or the TTS engine.

## Environment facts (verified 2026-10-28)

- Host: `shivangsh@somdutta-linux.local`, user UID 1001,
  `XDG_RUNTIME_DIR=/run/user/1001` (must be exported for pipewire/pulse tools).
- Audio: PipeWire 1.6.2 with PulseAudio compat. **Exactly one sink**:
  `alsa_output.pci-0000_00_1b.0.analog-stereo` (onboard analog). The NVIDIA
  HDMI sink is not exposed, so analog is the one wired to speakers.
- Installed: `espeak-ng`, `paplay`, `pw-play`, `ffplay`, `aplay`, `pactl`, `wpctl`.

## Gotchas

- **Muted or 0% sink = silence with exit code 0.** This was the actual cause of
  "I did not hear anything". Always check:

  ```sh
  pactl get-sink-mute  @DEFAULT_SINK@
  pactl get-sink-volume @DEFAULT_SINK@
  ```

  The script auto-unmutes and sets 70% when it finds mute/0%, and says so.
- **`paplay` returning 0 proves nothing.** Proof of audio flowing is
  `pactl list sinks short | grep analog` showing `RUNNING` while the clip plays.
- **Never conclude "nothing played" from a `media_player` entity state** — the
  HA/Sonos path returns HTTP 200 + `[]` and stays `idle` even when audio plays
  (snapshot/restore).
- **Quote safely.** The script base64-encodes text; don't inline user text into
  a shell string yourself.
- **Clean up.** Temp WAVs go to `/tmp` and are removed by a `trap`; keep that.
- **Password handling.** `$SSHPASS` only (`sshpass -e`), never in argv or in a
  file. Prefer an SSH key so no password is needed at all.

## Do not

- Never power off `switch.shivi_linux_box` or anything similar (see the HA
  hard rule). Speaking to the host is fine; shutting it down is not.
- Don't change the sink volume wildly or leave the user's audio muted without
  telling them what you changed.

## Radio / long playback

`say-on-host.sh` is for clips. For a stream, start VLC detached and verify with
sink-inputs, not with `pgrep -a cvlc` (the process is named `vlc`).

```sh
export XDG_RUNTIME_DIR=/run/user/1001
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
setsid nohup cvlc --intf dummy --no-video --quiet \
  --http-user-agent="$UA" --http-referrer="https://somafm.com/" \
  "https://ice1.somafm.com/bootliquor-128-mp3" >/tmp/radio.log 2>&1 &
```

- **SomaFM returns 403 without a browser User-Agent + Referer.** Verify a
  candidate stream with `curl -o /dev/null -w '%{http_code}' -r 0-4096` and
  expect **206 + audio/mpeg** before launching.
- Stop / inspect: `scripts/stop-host-audio.sh` / `... --status`.
- Working country-ish default: SomaFM **Boot Liquor** (Americana / alt-country),
  `https://ice1.somafm.com/bootliquor-128-mp3`.

## Sonos speakers (multi-room radio)

HA's `media_player.play_media` fails on Sonos with URL streams:
`UPnP error 714: Illegal MIME-Type` (it sends a bad protocolInfo), and
`audio/mpeg` is rejected by the integration. Use SoCo instead:

```sh
pip install --user --break-system-packages soco      # once, on the master host
ssh shivangsh@... 'python3 - "<url>" "Title"' < scripts/sonos-play-all.py
```

It discovers players over SSDP and calls `play_uri` with proper DIDL
(`<res protocolInfo="http-get:*:audio/mpeg:*">`). Verified 4/4: Dining Room
192.168.4.112, Living Room .124, Sitting Room .113, Upstairs .114.
Office Den Speaker is NOT Sonos (it accepts the HA play_media path).
