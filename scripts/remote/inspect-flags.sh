#!/usr/bin/env bash
# READ-ONLY, runs on the 3090 box: which speed-related options does this ComfyUI accept?
docker run --rm --entrypoint python comfyui-local:v0.42.1-sage2 main.py --help 2>&1 | grep -i -E -A3 "^\s+--fast|triton|kitchen|backend|fp16-|fp8|int8|cublas|autotune" | cut -c1-200 | head -60
