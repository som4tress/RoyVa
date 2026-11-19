#!/usr/bin/env bash
# Runs ON the 3090 box as root:  sudo bash install-boot-service.sh
# Installs gpu-power-limit.service: at every boot, enable persistence mode and cap the RTX 3090 at 300 W (the cap resets at each reboot otherwise).
# Undo:  sudo systemctl disable --now gpu-power-limit.service && sudo rm /etc/systemd/system/gpu-power-limit.service
set -e
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
WATTS="${1:-300}"
cat > /etc/systemd/system/gpu-power-limit.service <<UNIT
[Unit]
Description=Cap the NVIDIA GPU power limit at ${WATTS} W
After=nvidia-persistenced.service multi-user.target
Wants=nvidia-persistenced.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/nvidia-smi -pm 1
ExecStart=/usr/bin/nvidia-smi -pl ${WATTS}

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now gpu-power-limit.service
nvidia-smi -q -d POWER | grep -E "Current Power Limit|Default Power Limit"
systemctl is-enabled docker && echo "docker starts at boot: yes"
