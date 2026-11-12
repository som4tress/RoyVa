#!/usr/bin/env bash
. "$(dirname "$(readlink -f "$0")")/env.sh" || exit 1
cd $R/runtime/workspace
exec ${LARES_OPENCODE_BIN:-$HOME/.opencode/bin/opencode} serve --hostname 127.0.0.1 --port $ROYVA_PORT_OPENCODE
