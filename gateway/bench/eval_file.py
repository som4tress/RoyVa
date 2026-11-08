"""Run LLM classifiers on any eval file and print per-item results. Usage: eval_file.py <file.jsonl> name=url [name=url...]"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from royva_gateway import registry
from royva_gateway.classifiers import LLMClassifier
ROOT = Path(__file__).resolve().parent.parent
reg = registry.load(ROOT / "registry")
items = [json.loads(l) for l in open(sys.argv[1])]
clfs = [LLMClassifier(reg, spec.split("=", 1)[1], spec.split("=", 1)[0], fewshot=spec.split("=", 1)[0].endswith("+fs")) for spec in sys.argv[2:]]
score = {c.name: 0 for c in clfs}
for it in items:
    line = f"{it['id']} {it['text'][:58]:58s} expect={it['expected_intents']}"
    for c in clfs:
        p = c(it["text"], it["prior"], it["state"])
        ok = set(p.intents) == set(it["expected_intents"])
        score[c.name] += ok
        line += f"\n      {c.name:8s} {'OK ' if ok else 'MISS'} {p.intents}  ({p.latency_ms:.0f} ms)"
    print(line + (f"\n      note: {it['note']}" if it.get("note") else ""))
print("\nSCORES:", {k: f"{v}/{len(items)}" for k, v in score.items()})
