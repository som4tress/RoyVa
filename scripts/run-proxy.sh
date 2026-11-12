#!/usr/bin/env bash
. "$(dirname "$(readlink -f "$0")")/env.sh" || exit 1
export PROXY_PORT=$ROYVA_PORT_PROXY UPSTREAM=http://127.0.0.1:8000 CAPTURE_DIR=$R/captures
exec node $R/proxy/proxy.mjs
