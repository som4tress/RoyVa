#!/usr/bin/env bash
. /home/somdutta/RoyVa/scripts/env.sh || exit 1
cd $R/runtime/workspace
exec /home/somdutta/.opencode/bin/opencode serve --hostname 127.0.0.1 --port $ROYVA_PORT_OPENCODE
