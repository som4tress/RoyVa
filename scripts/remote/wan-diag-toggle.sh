#!/usr/bin/env bash
# Switches the Wan timing diagnostic off or on WITHOUT restarting ComfyUI (it checks a flag file on every call). Usage:  ! bash ~/RoyVa/scripts/remote/wan-diag-toggle.sh off   |   on
case "$1" in
  off) ssh somdutta@somdutta-linux.local 'touch ~/comfyui/data/wan_diag.off && echo "diagnostic OFF"' ;;
  on)  ssh somdutta@somdutta-linux.local 'rm -f ~/comfyui/data/wan_diag.off && echo "diagnostic ON"' ;;
  *) echo "usage: wan-diag-toggle.sh off|on" ;;
esac
