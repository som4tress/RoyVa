#!/usr/bin/env bash
# Compile a top-10 world breaking-news briefing and deliver it to Telegram.
# Scheduled via cron:  0 10 * * *  (runs daily at 10:00 local time)
set -uo pipefail

BOT_ENV="$HOME/.config/opencode/telegram/bot.env"
LOG="$HOME/.local/state/breaking-news-10am.log"
mkdir -p "$(dirname "$LOG")"

# shellcheck disable=SC1090
source "$BOT_ENV"
set -a
source "$HOME/llm-server/opencode.env"
source "$HOME/llm-server/api.env"
set +a

PROMPT='Compile the top 10 breaking news stories from around the world right now. Use web search across several outlets; prefer stories from the last 12 hours that are actually breaking, not features. Output ONLY a numbered list of 10 items, one line each: a short bold headline, then a dash, then one clause of detail. No preamble, no sources section, no closing remarks.'

OUT="$(cd "$HOME" && timeout 900 /home/somdutta/.opencode/bin/opencode run --server http://127.0.0.1:49374 \
  --model openrouter/deepseek/deepseek-v4.1-flash-1017 "$PROMPT" 2>/dev/null \
  | sed -e 's/\x1b\[[0-9;]*[a-zA-Z]//g' -e '/^> .*·/d' -e 's/\r$//')"

OUT="$(printf '%s\n' "$OUT" | sed -e '/^[[:space:]]*$/d')"

if [ -z "$OUT" ]; then
  OUT="⚠️ 10am briefing failed: opencode returned no output (see $LOG)"
fi

{
  echo "=== $(date '+%F %T %Z') ==="
  printf '%s\n' "$OUT"
} >> "$LOG"

send_chat() {
  local chat_id="$1" text="$2"
  # Telegram caps messages at 4096 chars; chunk on line boundaries.
  python3 - "$chat_id" "$text" "$TELEGRAM_BOT_TOKEN" <<'PY'
import sys, json, urllib.request
chat_id, text, token = sys.argv[1], sys.argv[2], sys.argv[3]
parts, cur = [], ""
for line in text.splitlines(True):
    if len(cur) + len(line) > 3900:
        parts.append(cur); cur = ""
    cur += line
if cur.strip():
    parts.append(cur)
for p in parts:
    data = json.dumps({"chat_id": chat_id, "text": p,
                       "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data,
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:
        print(f"send failed for {chat_id}: {e}", file=sys.stderr)
PY
}

# Registered chats: DM + group from telegram/state.json
for CHAT in 6064019420 -4680123561; do
  send_chat "$CHAT" "$OUT"
done
