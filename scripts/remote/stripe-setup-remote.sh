#!/usr/bin/env bash
# Runs ON the 3090 box as root. Stripes (RAID0) two EMPTY SATA partitions into /mnt/models and COPIES the ComfyUI models onto it. The original models on the root disk stay untouched.
#   sudo bash ~/stripe-setup.sh            -> DRY RUN: only safety checks, changes nothing
#   sudo bash ~/stripe-setup.sh --apply    -> asks you to type a confirmation, then does it (about 20-25 minutes, mostly the copy, rate-limited so the VMs sharing the source disk keep working)
# Needs (install WITHOUT recommends, otherwise apt may pull in a mail server): sudo apt install --no-install-recommends mdadm smartmontools rsync psmisc
# No reboot, no VM/ComfyUI restart. Only /dev/sda3 and /dev/sdb2 are ever wiped (override: STRIPE_A=... STRIPE_B=...).
# Changes on the system: /etc/fstab (old two lines removed, one added; backup kept), /etc/mdadm/mdadm.conf, /etc/udev/rules.d/99-md-readahead.rules, new dir /mnt/models, RAID0 /dev/md0.
# The one irreversible step is wiping those two partitions; the safety checks refuse unless both are empty (only lost+found), unmounted-safe and unused.
#
# ROLLBACK (if you want to undo): stop using the mount (remove COMFY_MOUNTS from the launcher), then
#   sudo umount /mnt/models; sudo mdadm --stop /dev/md0; sudo mdadm --zero-superblock /dev/sda3 /dev/sdb2
#   restore /etc/fstab from /etc/fstab.bak-stripe-* ; sudo mkfs.ext4 each partition again if you want the old empty "Secondary"/"Tertiary" disks back.
set -uo pipefail
APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1
A="${STRIPE_A:-/dev/sda3}"; B="${STRIPE_B:-/dev/sdb2}"; MD=/dev/md0; MNT=/mnt/models; CHUNK_K=64; RA_KB=4096
UUID_A="${STRIPE_UUID_A:-37435b5b-9d56-4680-84e6-29fed0a41a17}"; UUID_B="${STRIPE_UUID_B:-9633129b-57c0-43a4-bbb5-120d67f63b3d}"   # from the audit; the partitions must still carry these UUIDs
COPY_MBPS="${STRIPE_COPY_MBPS:-200}"   # rsync rate limit so the VMs on the source disk keep working (231 GB at 200 MB/s is about 20 minutes)
USER_NAME="${SUDO_USER:-$(id -un)}"; HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"; SRC="$HOME_DIR/comfyui/data/models"
STEP="preflight"

fail() { echo "ABORT: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }
warn() { echo "  WARNING: $*"; }

# Devices that must never be wiped: boot/EFI partitions, the root disk, the USB disk, anything mounted at / /boot /boot/efi.
deny_check() {
  case "$1" in
    /dev/sda1|/dev/sda2|/dev/sdb1|/dev/sdc*|/dev/sdd*|/dev/nvme*|/dev/mapper/*|/dev/md*) return 1 ;;
  esac
  local m; for m in / /boot /boot/efi; do [ "$(findmnt -n -o SOURCE "$m" 2>/dev/null)" = "$1" ] && return 1; done
  return 0
}

check_member() {   # $1 = partition device
  local dev="$1" mnt used n pids
  [ -b "$dev" ] || fail "$dev is not a block device"
  [ "$(lsblk -no TYPE "$dev" 2>/dev/null | head -1)" = "part" ] || fail "$dev is not a partition"
  deny_check "$dev" || fail "$dev is on the deny list (boot/EFI, root disk, USB disk, or not a plain SATA data partition)"
  local want; [ "$dev" = "$A" ] && want="$UUID_A" || want="$UUID_B"
  [ -n "$want" ] && [ "$(blkid -s UUID -o value "$dev")" = "$want" ] || fail "$dev does not carry the expected UUID $want (found: '$(blkid -s UUID -o value "$dev")'); the disks may have been re-ordered or changed since the audit"
  [ "$(lsblk -no FSTYPE "$dev" | head -1)" = "ext4" ] || fail "$dev filesystem is not plain ext4 (found: $(lsblk -no FSTYPE "$dev" | head -1)); refusing in case it is already RAID/LVM"
  mnt="$(findmnt -n -o TARGET -S "$dev" | head -1)"
  [ -n "$mnt" ] || fail "$dev is not mounted, so I cannot verify it is empty; mount it first"
  case "$mnt" in /mnt/*) ;; *) fail "$dev is mounted at $mnt, expected a /mnt/... data mount" ;; esac
  n="$(find "$mnt" -mindepth 1 -maxdepth 1 ! -name lost+found 2>/dev/null | wc -l)"
  [ "$n" = 0 ] || fail "$mnt is not empty ($n entries besides lost+found)"
  used="$(df --output=used -B1 "$mnt" | tail -1 | tr -d ' ')"
  [ "${used:-0}" -lt 200000000 ] || fail "$mnt uses $used bytes; expected an essentially empty disk"
  pids="$(fuser -m "$mnt" 2>/dev/null | tr -s ' ' | wc -w)"
  [ "$pids" = 0 ] || fail "$mnt has $pids process(es) with files open; stop them first"
  [ "$(blockdev --getsize64 "$dev")" -ge 400000000000 ] || fail "$dev is smaller than 400 GB"
  command -v smartctl >/dev/null 2>&1 || fail "smartctl is required (RAID0 doubles the failure exposure): sudo apt install --no-install-recommends smartmontools"
  smartctl -H "/dev/$(lsblk -no PKNAME "$dev" | head -1)" 2>/dev/null | grep -q -E 'PASSED|OK' && ok "$dev SMART health PASSED" || fail "$dev SMART health check did not pass"
  ok "$dev: ext4, partition, mounted at $mnt, empty ($used bytes used), no open files, $(( $(blockdev --getsize64 "$dev") / 1000000000 )) GB"
}

preflight() {
  [ "$(id -u)" = 0 ] || fail "run as root:  sudo bash $0 [--apply]"
  local c; for c in mdadm mkfs.ext4 wipefs blkid findmnt lsblk fuser blockdev getent rsync; do command -v "$c" >/dev/null 2>&1 || fail "missing command: $c (install with: sudo apt install --no-install-recommends mdadm smartmontools rsync psmisc)"; done
  [ "$A" != "$B" ] || fail "the two partitions are the same"
  check_member "$A"; check_member "$B"
  [ ! -e "$MD" ] || fail "$MD already exists"
  [ ! -e /dev/md127 ] || warn "/dev/md127 exists: another md array is present; make sure it is not one of ours"
  findmnt -n "$MNT" >/dev/null 2>&1 && fail "$MNT is already a mount point"
  grep -q "$MNT" /etc/fstab && fail "/etc/fstab already mentions $MNT"
  [ -d "$SRC" ] || fail "models folder not found: $SRC"
  local need have; need="$(du -sb "$SRC" | cut -f1)"; have=$(( $(blockdev --getsize64 "$A") < $(blockdev --getsize64 "$B") ? $(blockdev --getsize64 "$A") : $(blockdev --getsize64 "$B") ))
  have=$(( have * 2 ))
  [ "$have" -gt $(( need * 12 / 10 )) ] || fail "stripe (~$((have/1000000000)) GB) too small for the models (~$((need/1000000000)) GB)"
  ok "models folder $SRC = $((need/1000000000)) GB, stripe will hold ~$((have/1000000000)) GB"
  if command -v curl >/dev/null 2>&1; then
    if curl -fsS -m 3 http://127.0.0.1:8188/queue 2>/dev/null | grep -q '"queue_running": \[\[' ; then warn "ComfyUI is running a job right now: the copy will compete for the model disk; better to wait"; fi
  fi
  echo "  plan: wipe $A and $B, create RAID0 $MD (chunk ${CHUNK_K}K), ext4 at $MNT, copy $SRC at <= ${COPY_MBPS} MB/s, read-ahead ${RA_KB} KB, boot-time mount with nofail and ordered before docker"
}

[ "${STRIPE_SOURCE_ONLY:-0}" = 1 ] && return 0 2>/dev/null

echo "== preflight (changes nothing) =="; preflight
if [ "$APPLY" != 1 ]; then echo; echo "DRY RUN COMPLETE: all checks passed. To do it for real:  sudo bash $0 --apply"; exit 0; fi

echo; echo "This will ERASE $A and $B (verified empty above), create /dev/md0 and copy the models onto it. Type exactly:  STRIPE $A $B"
read -r -p "> " ans; [ "$ans" = "STRIPE $A $B" ] || fail "confirmation did not match; nothing was changed"

set -Eeuo pipefail
trap 'echo "FAILED during step: $STEP. fstab backup: /etc/fstab.bak-stripe-*. Do NOT reboot until you have checked /etc/fstab and the state of $A $B $MD." >&2' ERR
STAMP="$(date +%Y%m%d-%H%M%S)"

STEP="backup fstab"; cp -a /etc/fstab "/etc/fstab.bak-stripe-$STAMP"; ok "saved /etc/fstab.bak-stripe-$STAMP"
STEP="read UUIDs"; UA="$(blkid -s UUID -o value "$A")"; UB="$(blkid -s UUID -o value "$B")"; [ -n "$UA" ] && [ -n "$UB" ] || fail "empty UUID, refusing to edit fstab"
STEP="unmount"; umount "$(findmnt -n -o TARGET -S "$A" | head -1)"; umount "$(findmnt -n -o TARGET -S "$B" | head -1)"; ok "unmounted"
STEP="edit fstab"; sed -i "/$UA/d;/$UB/d" /etc/fstab; ok "removed the old fstab lines for $UA and $UB"
STEP="wipe signatures"; wipefs -a "$A" "$B" >/dev/null; ok "wiped"
STEP="create array"; mdadm --create "$MD" --level=0 --raid-devices=2 --chunk="$CHUNK_K" --metadata=1.2 --name=models --run "$A" "$B"; udevadm settle; sleep 2; [ -b "$MD" ] || fail "$MD did not appear"
STEP="make filesystem"; mkfs.ext4 -F -m 0 -L models -E stride=$((CHUNK_K/4)),stripe-width=$((CHUNK_K/4*2)),lazy_itable_init=0,lazy_journal_init=0 "$MD" >/dev/null; ok "ext4 created"
STEP="mount + fstab"; mkdir -p "$MNT"; NEWUUID="$(blkid -s UUID -o value "$MD")"
[ -n "$NEWUUID" ] || fail "empty UUID for $MD"
# x-systemd.before=docker.service: Docker auto-restarts ComfyUI after a reboot, so the models disk must be mounted first or the container would bind an empty folder
echo "UUID=$NEWUUID $MNT ext4 defaults,noatime,nofail,x-systemd.before=docker.service 0 2" >> /etc/fstab; mount "$MNT"; chown "$USER_NAME":"$USER_NAME" "$MNT"; ok "mounted at $MNT"
STEP="mdadm.conf"; mkdir -p /etc/mdadm; mdadm --detail --scan | grep -v -F -f <(grep -o 'UUID=[^ ]*' /etc/mdadm/mdadm.conf 2>/dev/null || echo NOMATCH) >> /etc/mdadm/mdadm.conf || true
STEP="read-ahead"; blockdev --setra $((RA_KB*2)) "$MD"
echo "SUBSYSTEM==\"block\", KERNEL==\"md*\", ACTION==\"add|change\", ATTR{bdi/read_ahead_kb}=\"$RA_KB\"" > /etc/udev/rules.d/99-md-readahead.rules; ok "read-ahead ${RA_KB} KB (also persistent via udev rule)"

STEP="copy models"; SRCDEV="$(lsblk -no PKNAME "$(findmnt -n -o SOURCE -T "$SRC")" | head -1)"
echo "copying $SRC -> $MNT, rate-limited to ${COPY_MBPS} MB/s (source disk ${SRCDEV:-?} I/O scheduler: $(cat /sys/block/${SRCDEV:-sdc}/queue/scheduler 2>/dev/null); ionice idle class only works with bfq, so the rate limit is what protects the VMs)"
ionice -c3 nice -n 19 rsync -a --info=progress2 --bwlimit=$((COPY_MBPS*1024)) "$SRC"/ "$MNT"/
STEP="verify copy"
( cd "$SRC" && find . -type f -printf '%s %P\n' | sort ) > /tmp/stripe-src.lst; ( cd "$MNT" && find . -type f -printf '%s %P\n' | sort ) > /tmp/stripe-dst.lst
diff -q /tmp/stripe-src.lst /tmp/stripe-dst.lst >/dev/null || fail "file list or sizes differ between $SRC and $MNT (see /tmp/stripe-src.lst vs /tmp/stripe-dst.lst)"
ok "all $(wc -l < /tmp/stripe-dst.lst) files copied with identical sizes"

STEP="speed test"; F="$(find "$MNT" -name 'wan2.2_i2v_high_noise_14B_int8_convrot.safetensors' | head -1)"
if [ -n "$F" ]; then
  O="$SRC/${F#$MNT/}"
  echo "quick read of the first 8 GiB of the high expert (may be partly cached; stripe-verify.sh does the proper cold test):"
  printf '  old disk (sdc): '; dd if="$O" of=/dev/null bs=16M count=512 2>&1 | tail -1 || true
  printf '  stripe        : '; dd if="$F" of=/dev/null bs=16M count=512 2>&1 | tail -1 || true
else warn "high expert file not found for the speed test"; fi

trap - ERR
cat <<EOF

DONE. Stripe mounted at $MNT (originals untouched in $SRC).
Next (on the machine where you run the launchers):
  ! bash ~/RoyVa/scripts/remote/comfy-up-stripe.sh      (ComfyUI with /mnt/models mounted over /data/models)
then rerun an episode and compare the first-call stalls (FLUX 8 s, experts 35 s, speech 39 s were the SATA-bound baseline); sample per-disk reads with disk-sample.sh at the same time.
If the stripe is ever NOT mounted after a reboot, ComfyUI must not run from it: use comfy-up-default.sh (original models on the root disk).
To go back to the original disk: ! bash ~/RoyVa/scripts/remote/comfy-up-default.sh
EOF
