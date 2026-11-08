#!/usr/bin/env bash
# Send the owner a Telegram message from the developer-assistant (Claude), and remember its message id so that replies
# are routed to the inbox (runtime/claude/inbox.jsonl) instead of starting an OpenCode session.
# Usage: scripts/notify.sh "text"
set -e
set -a; . /home/somdutta/.config/opencode/telegram/bot.env; set +a
export PATH=/home/somdutta/.nvm/versions/node/v24.22.1/bin:$PATH
export NOTIFY_TEXT="${NOTIFY_PREFIX-🤖 Claude: }$1" CLAUDE_DIR=/home/somdutta/RoyVa/runtime/claude
mkdir -p "$CLAUDE_DIR"
exec node --input-type=module -e '
import { readFileSync, writeFileSync } from "node:fs";
const token = process.env.TELEGRAM_BOT_TOKEN, owner = Number(process.env.TELEGRAM_ALLOWED_USER_IDS.split(",")[0].trim());
const r = await (await fetch(`https://api.telegram.org/bot${token}/sendMessage`, { method: "POST", headers: { "content-type": "application/json" },
  body: JSON.stringify({ chat_id: owner, text: process.env.NOTIFY_TEXT }) })).json();
if (!r.ok) { console.error("Telegram error:", r.error_code); process.exit(1); }
const f = process.env.CLAUDE_DIR + "/outbox.json"; let ids = []; try { ids = JSON.parse(readFileSync(f, "utf8")); } catch {}
ids.push(r.result.message_id); writeFileSync(f, JSON.stringify(ids.slice(-200)), { mode: 0o600 });
console.log("sent message", r.result.message_id);'
