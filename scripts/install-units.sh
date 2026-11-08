#!/usr/bin/env bash
# One-time setup so the whole RoyVa stack starts on boot. Run by you:  ! /home/somdutta/RoyVa/scripts/install-units.sh
set -e
R=/home/somdutta/RoyVa
mkdir -p ~/.config/systemd/user
for u in royva-proxy.service royva-opencode.service royva-router-9b.service royva-gateway.service royva-bridge.service royva.target; do
  ln -sf $R/systemd/$u ~/.config/systemd/user/$u
done
# Dev-run copies (scripts/supervise.sh) would hold the same ports: stop them before systemd takes over.
pkill -f "[s]cripts/supervise.sh" 2>/dev/null || true
pkill -f "[r]outer/Qwen3.5-9B" 2>/dev/null || true
pkill -f "[p]roxy/proxy.mjs" 2>/dev/null || true
pkill -f "[o]pencode serve --hostname 127.0.0.1 --port 49380" 2>/dev/null || true
pkill -f "[u]vicorn royva_gateway" 2>/dev/null || true
pkill -f "[R]oyVa/bridge/bridge.mjs" 2>/dev/null || true
# Only one process may long-poll the Telegram bot token: the old bridge must not start at boot.
systemctl --user disable --now opencode-telegram-vanilla.service 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable evo-llamacpp-agent.service royva.target
systemctl --user enable royva-proxy.service royva-opencode.service royva-router-9b.service royva-gateway.service royva-bridge.service
systemctl --user start royva.target
loginctl show-user "$USER" -p Linger 2>/dev/null || true      # must say Linger=yes so user services start at boot without a login
echo "Installed and started. Check:  $R/scripts/royva-status.sh"
