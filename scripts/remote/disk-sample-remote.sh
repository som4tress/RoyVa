#!/usr/bin/env bash
# Runs ON the box (via disk-sample.sh). Once a second: time and cumulative bytes read by sda, sdb, sdc and md0 (throughput = difference between rows).
echo "time sda_bytes sdb_bytes sdc_bytes md0_bytes"
while true; do
  awk -v t="$(date +%T)" '{ r[$3] = $6 } END { printf "%s %.0f %.0f %.0f %.0f\n", t, r["sda"]*512, r["sdb"]*512, r["sdc"]*512, r["md0"]*512 }' /proc/diskstats
  sleep 1
done
