#!/usr/bin/env bash
# Puts the box-side prompt length guard back ON with a ceiling of N characters (default 1000), restarts ComfyUI so it applies, and proves it.
# Run (the GPU must be idle):  ! bash ~/RoyVa/scripts/remote/prompt-guard-set.sh        or with another ceiling:  ! bash ~/RoyVa/scripts/remote/prompt-guard-set.sh 800
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; N="${1:-1000}"
bash "$D/prompt-guard.sh" || exit 1
COMFY_ENV="COMFY_MAX_PROMPT_CHARS=$N" bash "$D/comfy-up-default.sh" || exit 1
bash "$D/prompt-guard-verify.sh"
echo; echo "Expected in the guard's log: \"max\": $N and \"was\": 2004, \"sent\": at most $N"
