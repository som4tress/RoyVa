"""One line per saved load sample: GPU compute %, GPU clock, power, VRAM, CPU idle %, load average. Reads files written by load.sh."""
import re, sys
from pathlib import Path

print(f"{'run':34} {'gpu% avg/max':>13} {'MHz avg':>8} {'W avg':>6} {'VRAM MiB':>9} {'cpu idle%':>10} {'load1':>6}")
for f in sorted(sys.argv[1:]):
    t = Path(f).read_text(errors="replace")
    g = [l.split(", ") for l in t.splitlines() if re.match(r"\d{4}/\d\d/\d\d ", l)]
    def col(i, unit):
        return [float(r[i].replace(unit, "").strip()) for r in g if len(r) > i]
    util, mhz, w, mem = col(1, "%"), col(7, "MHz"), col(6, "W"), col(5, "MiB")
    idle = [int(l.split()[14]) for l in t.splitlines() if re.match(r"\s*\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+", l) and len(l.split()) >= 15][1:]
    la = re.search(r"load average: ([\d.]+)", t)
    avg = lambda x: sum(x) / len(x) if x else float("nan")
    print(f"{Path(f).stem:34} {avg(util):6.0f}/{max(util, default=0):<6.0f} {avg(mhz):8.0f} {avg(w):6.0f} {avg(mem):9.0f} {avg(idle):10.0f} {la.group(1) if la else '?':>6}")
