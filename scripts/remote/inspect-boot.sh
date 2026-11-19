#!/usr/bin/env bash
# READ-ONLY, runs on the 3090 box: why did it restart? Shows the last boots, whether the previous one ended cleanly, and any GPU / power / thermal kernel messages.
echo "== boots"; last -x -n 12 reboot shutdown 2>/dev/null | head -12
echo; echo "== last 25 lines of the previous boot (a clean shutdown shows stopping services; a power trip just stops)"
journalctl -b -1 -n 25 --no-pager 2>&1 | cut -c1-200
echo; echo "== GPU / power / thermal / machine-check messages in the previous boot"
journalctl -k -b -1 --no-pager 2>&1 | grep -i -E "xid|nvrm|thermal|mce|machine check|power|watchdog|oom|panic|reset" | tail -20 | cut -c1-200
echo; echo "== GPU power now"
nvidia-smi -q -d POWER | grep -i -E "power limit|default|max|min|draw" | head -8
echo; echo "== PSU hint: board / memory"
sudo -n true 2>/dev/null && echo "(sudo available)" || echo "(no passwordless sudo, fine)"
