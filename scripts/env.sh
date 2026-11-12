#!/usr/bin/env bash
# Shared environment for the RoyVa stack. Secrets are sourced from existing private files by path; never copied.
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Product/assistant names and deployment values come from lares.toml (see lares.example.toml); an already-set variable wins.
eval "$(python3 "$R/scripts/lares_config.py")" || return 1
export XDG_CONFIG_HOME=$R/runtime/config-root XDG_DATA_HOME=$R/runtime/data
export XDG_STATE_HOME=$R/runtime/state XDG_CACHE_HOME=$R/runtime/cache
export OPENCODE_CONFIG_DIR=$R/runtime/config OPENCODE_CONFIG_PROJECT_DISABLE=1 OPENCODE_DISABLE_CLAUDE_CODE=1
export PATH=${LARES_NODE_BIN:+$LARES_NODE_BIN:}$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
set -a; . "${LARES_LLM_DIR:-$HOME/llm-server}/api.env"; . "${LARES_LLM_DIR:-$HOME/llm-server}/ha.env"; set +a
if [ ! -f "$R/runtime/server.env" ]; then
  ( umask 077; printf 'OPENCODE_SERVER_PASSWORD=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')" > "$R/runtime/server.env" )
fi
set -a; . "$R/runtime/server.env"; set +a
export ROYVA_PORT_PROXY=8100 ROYVA_PORT_OPENCODE=49380
mkdir -p "$R/runtime/config" "$R/runtime/workspace" "$R/runtime/state" "$R/captures"
ln -sf "$R/config/opencode.json" "$R/runtime/config/opencode.json"

# Household and deployment values (default person, protected devices, remote hosts, remote transcription) live in lares.toml, not here.
