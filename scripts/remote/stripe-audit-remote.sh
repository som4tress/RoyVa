#!/usr/bin/env bash
# Runs ON the 3090 box (via stripe-audit.sh). READ-ONLY: nothing is written, mounted, unmounted or formatted. Lists what lives on the data partitions that would be
# wiped by a stripe, what is using them (VMs, containers, open files), how big the ComfyUI models are, and how busy each disk has been since boot.
# Test override: MOUNTS="/path1 /path2" bash stripe-audit-remote.sh
section() { echo; echo "== $1 =="; }

section "partitions and filesystems (lsblk -f: FSTYPE tells if a partition is plain ext4, LVM, RAID, ...)"
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT 2>/dev/null | grep -v -E '^(loop|zram)|snap'

if [ -z "${MOUNTS:-}" ]; then
  MOUNTS="$(lsblk -nr -o NAME,MOUNTPOINT 2>/dev/null | awk '$2 ~ /^\/mnt\// {print $2}')"
fi
section "candidate data mounts"
if [ -z "$MOUNTS" ]; then echo "none found under /mnt"; else for m in $MOUNTS; do findmnt -T "$m" -o TARGET,SOURCE,FSTYPE,OPTIONS 2>/dev/null | tail -1; df -h "$m" 2>/dev/null | tail -1; done; fi

for m in $MOUNTS; do
  section "contents of $m (first level, sizes; du limited to 90 s)"
  ls -la "$m" 2>&1 | head -40
  echo "-- size per top-level entry:"
  timeout 90 du -x -h --max-depth=1 "$m" 2>/dev/null | sort -h | tail -15 || echo "(du timed out or failed)"
  echo "-- files over 1 GB (typical VM disks / images: qcow2 vdi vmdk img iso raw):"
  timeout 60 find "$m" -xdev -type f -size +1G -printf '%s %p\n' 2>/dev/null | sort -nr | head -15 | awk '{printf "%7.1f GB  %s\n", $1/1073741824, substr($0, index($0,$2))}'
  echo "-- processes with files open there (fuser; may show only your own processes without root):"
  fuser -vm "$m" 2>&1 | head -15
done

section "virtual machines and containers that may use those disks"
echo "-- hypervisor processes (qemu/kvm/VirtualBox/libvirt) with any /mnt path on their command line:"
ps -eo pid,user,args 2>/dev/null | grep -i -E 'qemu|kvm|VBox|virtualbox|libvirt|vmware' | grep -v grep | cut -c1-260 | head -10 || true
[ -z "$(ps -eo args 2>/dev/null | grep -i -E 'qemu|kvm|VBox|libvirt' | grep -v grep)" ] && echo "(none visible)"
command -v VBoxManage >/dev/null 2>&1 && { echo "-- VirtualBox VMs:"; VBoxManage list vms 2>&1 | head; }
command -v virsh >/dev/null 2>&1 && { echo "-- libvirt VMs:"; virsh list --all 2>&1 | head; }
echo "-- docker containers and their bind mounts (only those touching /mnt or the model folder):"
if command -v docker >/dev/null 2>&1; then
  docker ps -a --format '{{.Names}}' 2>/dev/null | while read -r c; do
    docker inspect -f '{{.Name}}  state={{.State.Status}}  mounts: {{range .Mounts}}{{.Source}} {{end}}' "$c" 2>/dev/null
  done | grep -E '/mnt|comfyui' || echo "(no container mounts under /mnt or comfyui)"
else echo "(docker not available)"; fi

section "fstab entries that mention those mounts (so we know what is expected to be there at boot)"
grep -v '^#' /etc/fstab 2>/dev/null | grep -E '/mnt|UUID' | cut -c1-200

section "ComfyUI models: size and what is on the root disk"
M="$HOME/comfyui/data/models"
[ -d "$M" ] && { du -sh "$M" 2>/dev/null; du -h --max-depth=1 "$M" 2>/dev/null | sort -h | tail -8; } || echo "no $M"
df -h / 2>/dev/null | tail -1

section "how busy each disk has been since boot (sectors read/written from /proc/diskstats)"
awk '$3 ~ /^sd[a-z]$/ {printf "%-4s read %8.1f GB   written %8.1f GB\n", $3, $6*512/1073741824, $10*512/1073741824}' /proc/diskstats 2>/dev/null

section "what this audit could NOT see"
echo "- SMART health (needs root): run  sudo smartctl -a /dev/sda  and /dev/sdb  before trusting a disk with a stripe"
echo "- files owned by other users may be hidden from du/find/fuser without root"
