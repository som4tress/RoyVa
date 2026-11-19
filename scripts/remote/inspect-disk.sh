#!/usr/bin/env bash
# READ-ONLY, runs on the 3090 box: how fast can the model files be read? (Wan 14B experts are about 14 GB each; if ComfyUI has to re-read them from disk at every swap, that is slow.)
echo "== disks"; lsblk -d -o NAME,ROTA,TRAN,MODEL,SIZE 2>/dev/null; echo "(ROTA 1 = spinning disk, 0 = SSD/NVMe)"
echo; echo "== which disk holds the models"; df -h "$HOME/comfyui/data/models" | tail -1
echo; echo "== direct read speed of one Wan expert (first 3 GB, bypassing the page cache)"
F="$HOME/comfyui/data/models/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
dd if="$F" of=/dev/null bs=16M count=192 iflag=direct 2>&1 | tail -1
echo; echo "== memory now"; free -m | sed -n 1,2p
echo; echo "== ComfyUI container memory"; docker stats --no-stream --format 'mem {{.MemUsage}} ({{.MemPerc}})' comfyui-limited
