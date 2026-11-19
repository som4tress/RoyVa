#!/usr/bin/env bash
# Shrinks (or restores) the live memory of the two VMs with the virtio balloon. No restart, no pause, nothing persistent:
# the configured maximum (Haos 16G, pluto-vm 8G) is untouched, and a VM restart returns it to full size.
# Usage on the 3090 box:  bash vm-balloon.sh shrink | restore | status
# Safety: refuses to shrink a VM if the guest itself uses more than 60% of the target size.
set -u
HAOS_TARGET_MIB=6144      # 6 GiB for Home Assistant (it uses about 0.5 GiB now)
PLUTO_TARGET_MIB=3072     # 3 GiB for pluto-vm (it uses about 0.4 GiB now)
HAOS_FULL_MIB=16384
PLUTO_FULL_MIB=8192

stat() { virsh dommemstat "$1" 2>/dev/null | awk -v k="$2" '$1==k {print $2}'; }
show() {
  for vm in Haos pluto-vm; do
    a=$(stat $vm actual); u=$(stat $vm unused); r=$(stat $vm rss)
    echo "$vm: balloon=$((a/1024))MiB guest-unused=$((u/1024))MiB guest-used=$(((a-u)/1024))MiB host-rss=$((r/1024))MiB"
  done
  free -m | sed -n 2p
}
shrink_one() {   # name target_mib
  a=$(stat "$1" actual); u=$(stat "$1" unused)
  used_mib=$(( (a - u) / 1024 ))
  if [ $((used_mib * 100)) -gt $(( $2 * 60 )) ]; then echo "SKIP $1: guest uses ${used_mib}MiB, too much for $2MiB"; return; fi
  echo "$1 -> $2MiB (guest uses ${used_mib}MiB)"; virsh setmem "$1" "${2}M" --live
}
case "${1:-status}" in
  status)  show ;;
  shrink)  echo "--- before"; show; shrink_one Haos $HAOS_TARGET_MIB; shrink_one pluto-vm $PLUTO_TARGET_MIB; sleep 20; echo "--- after 20s"; show ;;
  restore) virsh setmem Haos "${HAOS_FULL_MIB}M" --live; virsh setmem pluto-vm "${PLUTO_FULL_MIB}M" --live; sleep 5; show ;;
  *) echo "usage: $0 shrink|restore|status"; exit 2 ;;
esac
