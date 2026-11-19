#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Switches the Wan timing diagnostic off or on WITHOUT restarting ComfyUI (it checks a flag file on every call). Usage:  ! bash ~/RoyVa/scripts/remote/wan-diag-toggle.sh off   |   on
case "$1" in
  off) ssh ${BOX_SSH} 'touch ~/comfyui/data/wan_diag.off && echo "diagnostic OFF"' ;;
  on)  ssh ${BOX_SSH} 'rm -f ~/comfyui/data/wan_diag.off && echo "diagnostic ON"' ;;
  *) echo "usage: wan-diag-toggle.sh off|on" ;;
esac
