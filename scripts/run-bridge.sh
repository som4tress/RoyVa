#!/usr/bin/env bash
. "$(dirname "$(readlink -f "$0")")/env.sh" || exit 1
set -a; . "${LARES_TELEGRAM_ENV:-$HOME/.config/opencode/telegram/bot.env}"; set +a
export OPENCODE_TG_URL=http://127.0.0.1:$ROYVA_PORT_OPENCODE OPENCODE_TG_DIR=$R/runtime/workspace
export OPENCODE_TG_STATE_FILE=$R/runtime/state/telegram.json WHISPER_TMP=$R/runtime/state/voice
export OPENCODE_TG_MODEL_LABEL='RoyVa test · Qwen3.6 35B-A3B Q8_0 · vanilla OpenCode v2.2.5'
export ROYVA_GATEWAY_URL=${ROYVA_GATEWAY_URL-http://127.0.0.1:8300}   # set empty to bypass the gateway
exec node $R/bridge/bridge.mjs
