#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# EXPERIMENT: reads model files once on the box HOST (outside the ComfyUI container's 24 GiB cgroup) so they sit in the shared page cache, then prints how much of each is cached.
# Uses reclaimable host page cache only (about the file sizes: hi expert 13.5 GB); the kernel drops it if the box needs the RAM. Reads at SATA speed, so ~35 s per 13.5 GB.
# Run:  ! bash ~/RoyVa/scripts/remote/cache-warm.sh [hi|lo|te|all]     (default hi; 'all' = both experts + text encoder = ~33 GB, too much for the free RAM: use one at a time)
W="${1:-hi}"
ssh ${BOX_SSH} "W='$W' bash -s" <<'R'
M="$HOME/comfyui/data/models"
case "$W" in
  hi)  N="wan2.2_i2v_high_noise_14B_int8_convrot.safetensors" ;;
  lo)  N="wan2.2_i2v_low_noise_14B_int8_convrot.safetensors" ;;
  te)  N="umt5_xxl_int8_convrot.safetensors" ;;
  all) N="wan2.2_i2v_high_noise_14B_int8_convrot.safetensors wan2.2_i2v_low_noise_14B_int8_convrot.safetensors umt5_xxl_int8_convrot.safetensors" ;;
  *) echo "usage: cache-warm.sh hi|lo|te|all"; exit 2 ;;
esac
echo "free before:"; free -m | awk 'NR==2{print "  available MB: " $7 "  free MB: " $4}'
for n in $N; do
  f="$(find "$M" -type f -name "$n" | head -1)"; [ -n "$f" ] || { echo "missing $n"; continue; }
  s=$(date +%s); cat "$f" > /dev/null; e=$(date +%s)
  echo "read $n in $((e-s)) s"
  fincore -b -n -o RES,SIZE "$f" | awk -v f="$n" '{printf "  cached %.2f / %.2f GB (%.0f%%)\n", $1/1073741824, $2/1073741824, 100*$1/$2}'
done
echo "free after:"; free -m | awk 'NR==2{print "  available MB: " $7 "  free MB: " $4}'
R
