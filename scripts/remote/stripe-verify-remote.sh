#!/usr/bin/env bash
# Runs ON the box (via stripe-verify.sh). READ-ONLY, no sudo needed: confirms the stripe's state after stripe-setup, then times COLD reads of the same model file from the old disk and from the stripe
# two ways: big sequential reads, and an mmap page-touch pass (which imitates how ComfyUI's loader pulls weights in).
section() { echo; echo "== $1 =="; }
section "fstab (non-comment lines; the old /mnt/<uuid> lines must be gone, the /mnt/models line present)"
grep -v '^#' /etc/fstab | grep -v '^$' | cut -c1-190
printf 'old partition lines still in fstab: %s (want 0)\n' "$(grep -c -E '37435b5b|9633129b' /etc/fstab)"
section "array"
cat /proc/mdstat
section "mount"
findmnt /mnt/models -o TARGET,SOURCE,FSTYPE,OPTIONS 2>&1; df -h /mnt/models | tail -1
section "read-ahead and persistence"
printf 'md0 read_ahead_kb now: '; cat /sys/block/md0/bdi/read_ahead_kb 2>&1
echo "udev rule:"; cat /etc/udev/rules.d/99-md-readahead.rules 2>&1
echo "mdadm.conf array lines:"; grep -i '^ARRAY' /etc/mdadm/mdadm.conf 2>&1
section "copied models"
ls -ld /mnt/models; ls /mnt/models; printf 'files: '; find /mnt/models -type f | wc -l
section "cold read speed: old disk (sdc) vs stripe, same file (8 GiB sequential, then 4 GiB mmap page-touch)"
python3 - <<'PY'
import mmap, os, time
REL = "diffusion_models/wan2.2_i2v_high_noise_14B_int8_convrot.safetensors"
OLD = os.path.expanduser("~/comfyui/data/models/") + REL
NEW = "/mnt/models/" + REL
def evict(fd): os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
def seq(path, nbytes=8 << 30, bs=16 << 20):
    fd = os.open(path, os.O_RDONLY); evict(fd); buf = bytearray(bs); n = 0; t = time.time()
    with os.fdopen(fd, "rb", buffering=0) as f:
        while n < nbytes:
            r = f.readinto(buf)
            if not r: break
            n += r
    dt = time.time() - t; return n / dt / 1e6, n / 1e9, dt
def mm(path, nbytes=4 << 30):
    fd = os.open(path, os.O_RDONLY); evict(fd); m = mmap.mmap(fd, 0, access=mmap.ACCESS_READ); s = 0; t = time.time()
    for off in range(0, min(nbytes, len(m)), 4096): s += m[off]
    dt = time.time() - t; os.close(fd); return min(nbytes, len(m)) / dt / 1e6, min(nbytes, len(m)) / 1e9, dt
for name, p in (("old disk (sdc)", OLD), ("stripe /mnt/models", NEW)):
    if not os.path.exists(p): print(f"{name}: file missing"); continue
    a = seq(p); b = mm(p)
    print(f"{name:20s} sequential: {a[0]:7.0f} MB/s ({a[1]:.1f} GB in {a[2]:.1f} s)   mmap page-touch: {b[0]:7.0f} MB/s ({b[1]:.1f} GB in {b[2]:.1f} s)")
PY
echo; echo "(baseline for comparison: the SATA ceiling measured earlier was ~467 MB/s)"
