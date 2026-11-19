#!/usr/bin/env bash
# Runs ON the 3090 box (via storage-check.sh). Read-only: reports disks, NVMe devices, link speeds, where the ComfyUI models live, and the motherboard model.
echo "== machine =="
for f in sys_vendor product_name board_vendor board_name bios_version; do printf '%-14s %s\n' "$f" "$(cat /sys/class/dmi/id/$f 2>/dev/null || echo '(not readable)')"; done

echo; echo "== block devices (TRAN: sata / nvme / usb; ROTA 0 = SSD, 1 = spinning disk) =="
lsblk -d -o NAME,TRAN,ROTA,SIZE,MODEL 2>/dev/null | grep -v -E '^(loop|ram|zram)'

echo; echo "== NVMe devices =="
if ls /sys/class/nvme/nvme* >/dev/null 2>&1; then
  for d in /sys/class/nvme/nvme*; do
    n=$(basename "$d"); addr=$(cat "$d/address" 2>/dev/null)
    printf '%s  model=%s  fw=%s  transport=%s  pci=%s\n' "$n" "$(cat $d/model 2>/dev/null | xargs)" "$(cat $d/firmware_rev 2>/dev/null | xargs)" "$(cat $d/transport 2>/dev/null)" "$addr"
    p="/sys/bus/pci/devices/$addr"
    [ -d "$p" ] && printf '   link now: %s x%s   link max: %s x%s\n' "$(cat $p/current_link_speed 2>/dev/null)" "$(cat $p/current_link_width 2>/dev/null)" "$(cat $p/max_link_speed 2>/dev/null)" "$(cat $p/max_link_width 2>/dev/null)"
  done
else
  echo "NONE: no NVMe drive is present on this machine"
fi

echo; echo "== PCI storage controllers =="
lspci -nn 2>/dev/null | grep -i -E 'non-volatile|nvme|sata|raid|mass storage' || echo "(lspci shows none, or lspci is not installed)"

echo; echo "== SATA link speed (6 Gbps = SATA III, about 550 MB/s at best) =="
ls /sys/class/ata_link/*/sata_spd >/dev/null 2>&1 && for f in /sys/class/ata_link/*/sata_spd; do printf '%s: %s\n' "$(basename $(dirname $f))" "$(cat $f)"; done || echo "(not available)"

echo; echo "== where the ComfyUI models live =="
M="$HOME/comfyui/data/models"
df -h "$M" 2>/dev/null | tail -1
findmnt -T "$M" -o TARGET,SOURCE,FSTYPE 2>/dev/null
lsblk -o NAME,TRAN,SIZE,MODEL,MOUNTPOINT 2>/dev/null | grep -v -E '^(loop|zram)|snap' | head -30

echo; echo "== slot table (dmidecode lists M.2 slots and whether they are in use; needs root) =="
if command -v dmidecode >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  sudo -n dmidecode -t slot 2>/dev/null | grep -E 'Designation|Type:|Current Usage|Bus Address' | head -60
else
  echo "(needs passwordless sudo, not available here: run  sudo dmidecode -t slot  on the box yourself, or give me the machine/board model above and I will look up its M.2 slots)"
fi
