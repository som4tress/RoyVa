#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# The photos of a person that the agent uploads as references (ref_<job>_<n>.jpg/png/webp) stay in ComfyUI's input folder on the shared 3090 box. This lists them (default) or deletes them.
# Run:  ! bash ~/RoyVa/scripts/remote/clean-reference-photos.sh            (list only)
#       ! bash ~/RoyVa/scripts/remote/clean-reference-photos.sh --delete   (remove them)
# It only touches files named ref_* in the input folder (found under ~/comfyui/data), never the model folders; the stills, latents and probe images of the agent do not match that name.
MODE="${1:-list}"
ssh ${BOX_SSH} "MODE='$MODE' bash -s" <<'R'
set -u
DIRS=$(find "$HOME/comfyui/data" -maxdepth 2 -type d -name input 2>/dev/null)
[ -z "$DIRS" ] && { echo "no ComfyUI input folder found under ~/comfyui/data"; exit 1; }
for d in $DIRS; do
  echo "== $d"
  find "$d" -maxdepth 1 -type f -name 'ref_*' -printf '%TY-%Tm-%Td %TH:%TM  %10s  %f\n' | sort
  n=$(find "$d" -maxdepth 1 -type f -name 'ref_*' | wc -l); echo "($n reference photo files)"
  if [ "$MODE" = "--delete" ]; then find "$d" -maxdepth 1 -type f -name 'ref_*' -delete; echo "deleted $n files"; fi
done
R
