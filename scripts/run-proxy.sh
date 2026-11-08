#!/usr/bin/env bash
. /home/somdutta/RoyVa/scripts/env.sh
export PROXY_PORT=$ROYVA_PORT_PROXY UPSTREAM=http://127.0.0.1:8000 CAPTURE_DIR=$R/captures
exec node $R/proxy/proxy.mjs
