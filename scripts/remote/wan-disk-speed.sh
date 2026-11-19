#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Read-only: how fast can the model stripe on the 3090 box really be read? Reads about 5 GB of the low-noise Wan expert in normal buffered reads of parts nobody has read recently (iflag=nocache drops each part from the cache afterwards; direct I/O is refused on this array), first one stream, then four parallel streams,
# and prints the read-ahead setting and the array layout. Compare with the ~630 MB/s that ComfyUI achieves while loading an expert (see runtime/diag/wanload-*). Run when the GPU is idle:  ! bash ~/RoyVa/scripts/remote/wan-disk-speed.sh
ssh ${BOX_SSH} 'F=/mnt/models/diffusion_models/wan2.2_i2v_low_noise_14B_int8_convrot.safetensors; ls -la $F | cut -c1-120
echo "--- array:"; cat /proc/mdstat | head -6; echo "read_ahead_kb md127: $(cat /sys/block/md127/queue/read_ahead_kb)"
echo "--- 1 stream (16 MB blocks, 2.4 GB):"; dd if=$F of=/dev/null bs=16M count=150 skip=600 iflag=nocache 2>&1 | tail -1
echo "--- 4 parallel streams (4 x 1.2 GB):"; for k in 0 1 2 3; do dd if=$F of=/dev/null bs=16M count=75 skip=$((k*160+10)) iflag=nocache 2>&1 | tail -1 & done; wait'
