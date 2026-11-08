#!/usr/bin/env bash
# Link RoyVa units into the user systemd dir. Run once, by you:  ! /home/somdutta/RoyVa/scripts/install-units.sh
set -e
mkdir -p ~/.config/systemd/user
for u in royva-proxy.service royva-opencode.service royva-router-9b.service royva-router-4b.service royva-gateway.service royva-bridge.service royva.target; do
  ln -sf /home/somdutta/RoyVa/systemd/$u ~/.config/systemd/user/$u
done
systemctl --user daemon-reload
echo "installed. Start everything:   systemctl --user start royva.target"
echo "Stop everything:               systemctl --user stop royva.target"
echo "(restore old bridge:           systemctl --user start opencode-telegram-vanilla.service)"
