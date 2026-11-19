#!/usr/bin/env bash
# Run:  ! bash ~/RoyVa/scripts/remote/pcie.sh   Read-only: samples GPU PCIe gen/width and utilisation for 40 s (run while a job is sampling).
ssh somdutta@somdutta-linux.local "for i in \$(seq 1 20); do nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.width.current,utilization.gpu,memory.used --format=csv,noheader; sleep 2; done"
