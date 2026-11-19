#!/usr/bin/env bash
# Runs ON the 3090 box. Builds comfyui-local:v0.42.1-gcc = the existing image + a C compiler (Triton needs one for SageAttention). The original image is untouched.
# Then start ComfyUI from it with:  COMFY_IMAGE=comfyui-local:v0.42.1-gcc COMFY_SAGE=1 bash ~/RoyVa/scripts/remote/comfy-up.sh
set -e
BASE=comfyui-local:v0.42.1; NEW=comfyui-local:v0.42.1-gcc
echo "base image OS:"; docker run --rm --entrypoint sh "$BASE" -c '. /etc/os-release; echo "$PRETTY_NAME"; id -un; which python'
printf 'FROM %s\nUSER root\nRUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*\n' "$BASE" > /tmp/Dockerfile.gcc
docker build -q -t "$NEW" -f /tmp/Dockerfile.gcc /tmp
echo "built $NEW. test as the same non-root user the container uses:"
docker run --rm --user "$(id -u):$(id -g)" --entrypoint sh "$NEW" -c 'gcc --version | head -1; echo "int main(){return 0;}" > /tmp/t.c && gcc /tmp/t.c -o /tmp/t && echo compile-ok'
docker image ls comfyui-local --format '{{.Repository}}:{{.Tag}}  {{.Size}}'
