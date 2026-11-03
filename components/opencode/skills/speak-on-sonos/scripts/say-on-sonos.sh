#!/usr/bin/env bash
# say-on-sonos.sh — read text aloud on any Wi-Fi/AirPlay speaker exposed in Home Assistant.
# Verified 2026-10-30. Avoids the silent-tts.speak and UPnP-714 traps.
set -uo pipefail

HA="https://som4tress.duckdns.org:8123"
TARGET="living room"
VOLUME="0.30"
PORT="8770"
STOP=0
USE_WAV=0
LIST=0
ALL=0
DRYRUN=0
COORD=""
SRC=""

while getopts "e:c:v:p:slanh" opt; do
  case "$opt" in
    e) TARGET="$OPTARG" ;;
    c) COORD="$OPTARG" ;;
    v) VOLUME="$OPTARG" ;;
    p) PORT="$OPTARG" ;;
    s) STOP=1 ;;
    l) LIST=1 ;;
    a) ALL=1 ;;
    n) DRYRUN=1 ;;
    h) sed -n '2,10p' "$0"; exit 0 ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND-1))
[[ "${1:-}" == "--wav" ]] && { USE_WAV=1; shift; }
SRC="${1:-}"
TDIR="/tmp/opencode/sonosp"
mkdir -p "$TDIR"

TOK="${HA_TOKEN:-}"
if [[ -z "$TOK" ]]; then
  TOK="$(bash -lc 'grep -ho "eyJ[A-Za-z0-9._-]*" ~/.zshrc ~/.bashrc ~/.profile 2>/dev/null | head -1' || true)"
fi
[[ -n "$TOK" ]] || { echo "no HA_TOKEN found" >&2; exit 1; }

haget() { curl -s -m 30 -H "Authorization: Bearer $TOK" "$HA$1"; }
apisvc() { curl -s -m 60 -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' -d "$1" "$HA/api/services/$2" >/dev/null 2>&1 || true; }

# ---- speaker list (only players that accept play_media + volume) ----
speakers() {
  haget /api/states | python3 -c '
import sys,json
for s in json.load(sys.stdin):
    if not s["entity_id"].startswith("media_player."): continue
    a=s["attributes"]; sf=a.get("supported_features") or 0
    if not (sf & 512) or a.get("volume_level") is None: continue   # PLAY_MEDIA + VOLUME_SET
    print("%s\t%s\t%s" % (s["entity_id"], a.get("friendly_name") or s["entity_id"], s["state"]))
'
}

if [[ "$LIST" == "1" ]]; then
  printf '%-42s %-24s %s\n' ENTITY NAME STATE
  speakers | while IFS=$'\t' read -r e n st; do printf '%-42s %-24s %s\n' "$e" "$n" "$st"; done
  exit 0
fi

resolve() { # friendly-ish name -> entity_id
  local want="$1"
  [[ "$want" == media_player.* ]] && { echo "$want"; return; }
  local q; q="$(echo "$want" | tr 'A-Z' 'a-z' | sed 's/all//g;s/speaker//g;s/the //g' | xargs)"
  speakers | python3 -c '
import sys,re
q=sys.argv[1]
rows=[l.rstrip("\n").split("\t") for l in sys.stdin if l.strip()]
def norm(x): return re.sub(r"[^a-z0-9 ]","",x.lower()).replace("speaker","").strip()
q=norm(q)
best=None
for e,n,st in rows:
    nn=norm(n); en=norm(e.replace("media_player.","").replace("_"," "))
    if q and (q in nn or nn in q or q in en or en in q):
        best=(e,n); break
if not best and rows: best=(rows[0][0],rows[0][1])
if best: print(best[0])
' "$q"
}

if [[ "$STOP" == "1" ]]; then
  if [[ "$ALL" == "1" ]]; then
    speakers | cut -f1 | while read -r e; do apisvc "{\"entity_id\":\"$e\"}" media_player/media_stop; done
    ids="$(speakers | cut -f1 | python3 -c 'import sys,json;print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))')"
    apisvc "{\"entity_id\":$ids}" media_player/unjoin
    echo "stopped and unjoined all speakers"; exit 0
  fi
  ENT="$(resolve "$TARGET")"
  [[ -n "$ENT" ]] || { echo "no matching speaker for '$TARGET'" >&2; exit 1; }
  apisvc "{\"entity_id\":\"$ENT\"}" media_player/media_stop
  echo "stopped $ENT"
  exit 0
fi

if [[ -z "$SRC" && "$DRYRUN" != "1" ]]; then echo "usage: $0 [-e SPEAKER] [-v VOLUME] [-a] [-l] [-n] [-s] [--wav] FILE_OR_TEXT" >&2; exit 2; fi

COORD_ENT="$(resolve "${COORD:-$( [[ "$ALL" == "1" ]] && echo "living room" || echo "$TARGET") }")"
MEMBERS=()
if [[ "$ALL" == "1" ]]; then
  while read -r e; do [[ "$e" == "$COORD_ENT" ]] || MEMBERS+=("$e"); done < <(speakers | cut -f1)
else
  COORD_ENT="$(resolve "$TARGET")"
fi
[[ -n "$COORD_ENT" ]] || { echo "no matching speaker for '$TARGET' (try -l)" >&2; exit 1; }
ENTITIES=("$COORD_ENT" "${MEMBERS[@]:-}")

if [[ "$DRYRUN" == "1" ]]; then
  echo "coordinator: $COORD_ENT"; for m in "${MEMBERS[@]:-}"; do [[ -n "$m" ]] && echo "  syncs: $m"; done; exit 0
fi

# ---- render audio ----
if [[ -f "$SRC" ]]; then TEXT="$(cat "$SRC")"; else TEXT="$SRC"; fi
TXT="$TDIR/speech.txt"; printf '%s\n' "$TEXT" > "$TXT"

if [[ "$USE_WAV" == "1" ]]; then
  command -v espeak-ng >/dev/null || { echo "espeak-ng missing" >&2; exit 1; }
  espeak-ng -v en-us -s 158 -w "$TDIR/speech.wav" -f "$TXT"
  FILE="$TDIR/speech.wav"
else
  python3 - "$TXT" "$TDIR/speech.mp3" <<'PY'
import re,sys,time,urllib.parse,urllib.request,os
txt=open(sys.argv[1]).read().replace('\n',' ')
sents=re.split(r'(?<=[.!?])\s+', txt.strip())
chunks=[]; cur=''
for s in sents:
    if len(cur)+len(s)+1<=180: cur=(cur+' '+s).strip()
    else:
        if cur: chunks.append(cur)
        while len(s)>180: chunks.append(s[:180]); s=s[180:]
        cur=s
if cur: chunks.append(cur)
out=open(sys.argv[2],'wb'); bad=0
for c in chunks:
    url='https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=en&q='+urllib.parse.quote(c)
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    for _ in range(3):
        try:
            d=urllib.request.urlopen(req,timeout=25).read()
            if d[:2] in (b'\xff\xfb',b'\xff\xf3',b'ID'):
                out.write(d); break
        except Exception:
            time.sleep(1)
    else:
        bad+=1
    time.sleep(0.15)
out.close()
print(f"[speak-on-sonos] {len(chunks)} chunks, {bad} failed, {os.path.getsize(sys.argv[2])//1024} KB")
PY
  FILE="$TDIR/speech.mp3"
fi

IP="$(ip -4 addr show scope global | grep -oP 'inet \K192\.168\.[0-9.]+' | head -1)"
[[ -n "$IP" ]] || IP="$(ip -4 addr show scope global | grep -oP 'inet \K[0-9.]+' | head -1)"
NAME="$(basename "$FILE")"

if ! curl -s -m 3 -o /dev/null -w '%{http_code}' "http://$IP:$PORT/$NAME" | grep -q 200; then
  pkill -f "http.server $PORT --bind" 2>/dev/null || true
  sleep 0.3
  nohup python3 -m http.server "$PORT" --bind 0.0.0.0 --directory "$TDIR" >"$TDIR/server.log" 2>&1 &
  sleep 1
fi

# ---- play on coordinator, then sync the rest to it (real Sonos/AirPlay group) ----
for ENT in "$COORD_ENT" "${MEMBERS[@]:-}"; do
  [[ -n "$ENT" ]] && apisvc "{\"entity_id\":\"$ENT\",\"volume_level\":$VOLUME}" media_player/volume_set
done

DUR=0
for attempt in 1 2; do
  curl -s -m 60 -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
    -d "{\"entity_id\":\"$COORD_ENT\",\"media_content_id\":\"http://$IP:$PORT/$NAME\",\"media_content_type\":\"music\"}" \
    "$HA/api/services/media_player/play_media" >/dev/null 2>&1
  sleep 3
  DUR="$(haget "/api/states/$COORD_ENT" | python3 -c 'import sys,json;a=json.load(sys.stdin)["attributes"];print(int(a.get("media_duration") or 0))' 2>/dev/null || echo 0)"
  [[ "${DUR:-0}" -gt 0 ]] && break
  sleep 1
done

if [[ "${DUR:-0}" -le 0 ]]; then
  echo "no playback on $COORD_ENT" >&2
  exit 1
fi
printf 'playing on %s at %s%% — %dm %02ds\n' "$COORD_ENT" "$(python3 -c "print(round($VOLUME*100))")" $((DUR/60)) $((DUR%60))

if [[ ${#MEMBERS[@]} -gt 0 ]]; then
  # Grow the group one member at a time, passing the current membership each time.
  # (A single multi-member join call does not stick with HA's Sonos integration.)
  joined=("$COORD_ENT")
  for m in "${MEMBERS[@]}"; do
    gm="$(printf '%s\n' "${joined[@]}" | python3 -c 'import sys,json;print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))')"
    curl -s -m 30 -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
      -d "{\"entity_id\":\"$m\",\"group_members\":$gm}" "$HA/api/services/media_player/join" >/dev/null 2>&1
    sleep 1.5
    if haget "/api/states/$COORD_ENT" | grep -q "\"$m\""; then
      joined+=("$m")
    else
      echo "  could not sync: $m (not groupable / offline)" >&2
    fi
  done
  echo "group: ${#joined[@]} speakers synced to $COORD_ENT"
fi
