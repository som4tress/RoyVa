#!/usr/bin/env bash
# READ-ONLY, runs on the 3090 box: follow-up to inspect-boot.sh. What happened in the last minutes before the box stopped (hostapd spam filtered out), and is the GPU healthy now?
echo "== boots"; journalctl --list-boots --no-pager 2>&1 | tail -4; echo "up since: $(uptime -s)"; date
for B in -2 -1; do
  echo; echo "== boot $B: the last 22 lines before it stopped (hostapd, snapd and firmware-notifier noise removed)"
  journalctl -b $B --no-pager 2>&1 | grep -v -E "hostapd|snapd-desktop|firmware-notifier|asynchronous suspension|dbus_client|notifications_client|future.dart|firmware_notifier" | tail -22 | cut -c1-200
done
echo; echo "== this boot: unclean-shutdown / recovery / watchdog / MCE hints"
journalctl -k -b 0 --no-pager 2>&1 | grep -i -E "recover|unclean|not properly|orphan|mce|watchdog|pstore|reset reason|xid|nvrm" | head -12 | cut -c1-200
ls /sys/fs/pstore /var/lib/systemd/pstore 2>/dev/null | head
echo; echo "== GPU now: temperature, power, throttle reasons"
nvidia-smi --query-gpu=name,temperature.gpu,power.draw,power.limit,clocks_throttle_reasons.active,pcie.link.gen.current,pcie.link.width.current --format=csv
echo; echo "== ComfyUI container"
docker inspect -f 'OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}} Started={{.State.StartedAt}} Finished={{.State.FinishedAt}}' comfyui-limited 2>&1
docker logs --tail 8 comfyui-limited 2>&1 | cut -c1-200
