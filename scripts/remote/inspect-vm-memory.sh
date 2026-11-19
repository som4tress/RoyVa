#!/usr/bin/env bash
# READ-ONLY: how much memory the Home Assistant VM (and the other VMs) are configured with versus really using.
# Changes nothing. Run:  ! ssh <user>@<box> 'bash -s' < ~/RoyVa/scripts/remote/inspect-vm-memory.sh
for vm in $(virsh list --all --name); do
  echo "=================== $vm"
  virsh dominfo "$vm" 2>&1 | grep -E "State|CPU\(s\)|Max memory|Used memory|Autostart"
  echo "-- config (memory / balloon / hugepages / cpu)"
  virsh dumpxml "$vm" 2>&1 | grep -E "<memory|<currentMemory|<memballoon|<hugepages|<vcpu|<memoryBacking|<locked"
  echo "-- what the guest reports (needs the balloon driver)"
  virsh dommemstat "$vm" 2>&1
done
echo "=================== host"
free -m
grep -E "^(MemAvailable|Cached|AnonHugePages|Hugepagesize|HugePages_Total)" /proc/meminfo
ps -o pid,rss,etime,args -C qemu-system-x86_64 --sort=-rss 2>/dev/null | cut -c1-120
