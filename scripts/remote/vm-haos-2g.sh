#!/usr/bin/env bash
# Runs ON the 3090 box (via haos-2g.sh):  bash vm-haos-2g.sh check | apply
# check : read-only. Shows the VM's configured and real memory and whether 2 GiB is safe (guest must use less than 60% of it).
# apply : saves the VM definition, shuts Haos down gracefully (never forced), sets BOTH the maximum and the current memory to 2 GiB in its persistent config, starts it again, and prints the result.
#         Home Assistant is offline for about a minute or two. Undo: bash vm-haos-2g.sh restore   (puts the saved definition back, 16 GiB, and restarts)
set -u
VM=Haos; TARGET_MIB=2048; BACKUP="$HOME/${VM}-before-2g.xml"
stat() { virsh dommemstat "$VM" 2>/dev/null | awk -v k="$1" '$1==k {print $2}'; }
state() { virsh domstate "$VM" 2>/dev/null | head -1; }
waitfor() {  # state timeout_s
  for _ in $(seq 1 "$2"); do [ "$(state)" = "$1" ] && return 0; sleep 1; done; return 1
}
show() { virsh dominfo "$VM" | grep -E "State|Max memory|Used memory"; echo "guest: balloon=$(( $(stat actual) / 1024 ))MiB unused=$(( $(stat unused) / 1024 ))MiB host-rss=$(( $(stat rss) / 1024 ))MiB"; }
case "${1:-check}" in
  check)
    show; used=$(( ($(stat actual) - $(stat unused)) / 1024 ))
    if [ $((used * 100)) -gt $((TARGET_MIB * 60)) ]; then echo "NOT SAFE: the guest uses ${used}MiB, more than 60% of ${TARGET_MIB}MiB"; exit 1; fi
    echo "OK: the guest uses ${used}MiB, safe for ${TARGET_MIB}MiB" ;;
  apply)
    [ "$(state)" = "running" ] || { echo "stop: $VM is '$(state)', expected running"; exit 1; }
    used=$(( ($(stat actual) - $(stat unused)) / 1024 ))
    [ $((used * 100)) -le $((TARGET_MIB * 60)) ] || { echo "stop: the guest uses ${used}MiB, too much for ${TARGET_MIB}MiB"; exit 1; }
    virsh dumpxml "$VM" --inactive > "$BACKUP" && echo "definition saved: $BACKUP" || { echo "stop: could not save the definition"; exit 1; }
    echo "shutting down $VM (graceful, up to 3 minutes)..."; virsh shutdown "$VM"
    waitfor "shut off" 180 || { echo "stop: $VM did not shut down in 3 minutes. Nothing was forced and nothing was changed; it may still be shutting down. Check: virsh domstate $VM"; exit 1; }
    virsh setmem "$VM" "${TARGET_MIB}M" --config && virsh setmaxmem "$VM" "${TARGET_MIB}M" --config || { echo "stop: could not set memory; starting $VM unchanged"; virsh start "$VM"; exit 1; }
    virsh start "$VM"; waitfor "running" 60 || { echo "$VM did not report running within 60s: check virsh domstate $VM"; exit 1; }
    echo "started; waiting 60s for the guest to come up..."; sleep 60; show ;;
  restore)
    [ -f "$BACKUP" ] || { echo "no backup at $BACKUP"; exit 1; }
    [ "$(state)" = "running" ] && { virsh shutdown "$VM"; waitfor "shut off" 180 || { echo "stop: did not shut down in 3 minutes, nothing forced"; exit 1; }; }
    virsh define "$BACKUP" && virsh start "$VM" && sleep 30 && show ;;
  *) echo "usage: $0 check|apply|restore"; exit 2 ;;
esac
