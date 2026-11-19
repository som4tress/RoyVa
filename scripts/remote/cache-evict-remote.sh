#!/usr/bin/env bash
# Runs ON the box (via cache-evict.sh). Asks the kernel to drop the page-cache pages of every model file (old disk and stripe) so the next run is a true cold start. No sudo, nothing is written or deleted.
python3 - <<'PY'
import os
n = 0
for root in (os.path.expanduser("~/comfyui/data/models"), "/mnt/models"):
    for d, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(d, f)
            try:
                fd = os.open(p, os.O_RDONLY); os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED); os.close(fd); n += 1
            except OSError:
                pass
print(f"evicted cached pages of {n} model files")
PY
free -m | awk 'NR<=2'
