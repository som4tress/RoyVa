#!/usr/bin/env bash
# Serve one small router model with llama.cpp. Usage: run-router-model.sh <emb|llm> <gguf> <port>
set -e
KIND=$1; FILE=$2; PORT=$3
L=/home/somdutta/llm-server/llamacpp
export LD_LIBRARY_PATH=$L/compat/usr/lib/x86_64-linux-gnu:$L/llama-b12110
COMMON="--model /home/somdutta/llm-server/models/router/$FILE --host 127.0.0.1 --port $PORT --n-gpu-layers 999 --flash-attn on --ctx-size 8192 --parallel 2 --threads 8 --load-mode mmap --fit off"
if [ "$KIND" = emb ]; then
  exec $L/llama-b12110/llama-server $COMMON --embedding --pooling last --batch-size 512 --ubatch-size 512
else
  exec $L/llama-b12110/llama-server $COMMON --jinja --reasoning off --cache-prompt --temp 0 --batch-size 1024 --ubatch-size 512
fi
