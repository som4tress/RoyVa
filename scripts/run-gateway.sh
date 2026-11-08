#!/usr/bin/env bash
. /home/somdutta/RoyVa/scripts/env.sh
cd $R/gateway
exec ./.venv/bin/python -m uvicorn royva_gateway.app:app --host 127.0.0.1 --port 8300 --log-level info
