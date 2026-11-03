---
name: Speak On Sonos
description: Read long text aloud (news briefings, articles, alerts) on any Wi-Fi/AirPlay speaker exposed in Home Assistant — living room, dining, sitting room, upstairs, office/den — in a natural female voice at a set volume. Use for any "read this out / play the news on the <room> speaker" request. One command, no trial-and-error.
---

# Speak long text on any AirPlay / Wi-Fi speaker

```sh
~/.config/opencode/skills/speak-on-sonos/scripts/say-on-sonos.sh [options] FILE_OR_TEXT
```

Default: `living room` speaker, volume `0.30`, Google Translate US English (natural female).

The script enumerates speakers from Home Assistant at run time, so **any AirPlay/Wi-Fi
speaker that HA exposes with play_media + volume is automatically usable** — no code
change when a new one is added.

```sh
say-on-sonos.sh -l                       # list usable speakers
say-on-sonos.sh -n -e dining             # dry run: which entity matches
say-on-sonos.sh -e upstairs /tmp/x.txt   # speak on the upstairs speaker, 30%
say-on-sonos.sh -a -v 0.4 /tmp/x.txt     # whole-home: one coordinator, rest joined to it
say-on-sonos.sh -a -c upstairs /tmp/x.txt # same, but upstairs is the sync master
say-on-sonos.sh -s                       # stop living room
say-on-sonos.sh -s -a                    # stop all
```

| Flag | Meaning |
| --- | --- |
| `-e NAME` | speaker by room words (`living room`, `dining`, `sitting room`, `upstairs`, `office`, `den`) or a full `media_player.*` entity |
| `-v 0.30` | volume 0-1 |
| `-a` | all groupable speakers, synced to one coordinator (true Sonos group, not parallel playback) |
| `-c NAME` | coordinator / sync master for `-a` (default: `living room`) |
| `-l` | list speakers |
| `-n` | dry run, print matched entity |
| `-s` | stop |
| `-p PORT` | local HTTP port (default 8770) |
| `--wav` | espeak-ng offline fallback (robotic — only if internet is down) |

Currently registered: Living Room, Dining Room, Sitting Room, Upstairs, Office Den.
TV entities are skipped (they advertise no play_media/volume).

## How it works

1. Split text into <=180-char chunks on sentence boundaries.
2. Fetch each chunk from Google Translate TTS (`client=tw-ob`, `User-Agent: Mozilla/5.0`)
   → MPEG frames, 64 kbps 24 kHz mono.
3. Binary-concat into one `speech.mp3`.
4. Serve over LAN: `python3 -m http.server --bind 0.0.0.0 --directory /tmp/opencode/sonosp`.
5. Per speaker: `volume_set` on the coordinator, `play_media` on the coordinator only
   (`media_content_type: music`, `http://<LAN-IP>:PORT/speech.mp3`), verify `playing` +
   `media_duration`, retry once.
6. Multi-room: **grow the Sonos group one member at a time** — join member M with
   `group_members: [coordinator, ...already joined]`, re-checking the coordinator's
   `group_members` after each step. Audio then comes from the group, so it is
   time-aligned by Sonos/AirPlay, not two independent streams.

## Grouping pitfalls

- A single `media_player.join` call with several `entity_id`s and one coordinator
  **does not stick** on this Sonos integration — members evict each other. Grow the
  group incrementally as above.
- Pass the *whole current membership* in `group_members` each time, or earlier members
  get dropped.
- **Office Den Speaker cannot join a group** (no `group_members` attribute). Skip it and
  say so — never play it as a parallel, out-of-sync stream.
- `-a -s` stops and unjoins every speaker, so the next request starts from a clean state.

## Hard-won pitfalls — do not repeat these

- **`tts.speak` / `google_translate_say` to a Sonos/AirPlay entity silently does nothing.**
  HTTP 200, player stays `idle`. Always use the file + LAN URL route.
- **Third-party stream URLs fail** with `UPnP 714 Illegal MIME-Type`. Only serve files
  you generated locally.
- **`ffmpeg` has no MP3 encoder here**, so espeak→mp3 breaks. Google TTS already returns
  MP3 — concat the bytes. For `--wav`, serve the WAV directly (`audio/x-wav` is accepted).
- **`espeak-ng` was rejected as "robotic".** Never make it the default voice.
- `media_title` stays null for URL playback — that is normal; judge success by state +
  `media_duration`.
- The HTTP server must stay up for the whole clip; it is re-used across runs. If the
  served file 404s, the script restarts it on the same port.
- Long clips are fine (9m42s tested). Announce the duration when you start one.
