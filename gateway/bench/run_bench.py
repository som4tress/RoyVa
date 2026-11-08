"""Benchmark router classifiers on the held-out eval set.
Usage: python bench/run_bench.py --emb http://127.0.0.1:8201 --llm 4B=http://127.0.0.1:8202 [--llm 9B=http://127.0.0.1:8203]
Embedding thresholds and hybrid thresholds are calibrated on the DEV half only; every number reported is on the TEST half."""
import argparse
import itertools
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from royva_gateway import registry
from royva_gateway.classifiers import EmbeddingClassifier, LLMClassifier, RulesClassifier, turn_state, Prediction, _mode

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--emb")
ap.add_argument("--llm", action="append", default=[], help="name=url")
ap.add_argument("--llm-key", default="")
args = ap.parse_args()

reg = registry.load(ROOT / "registry")
items = [json.loads(l) for l in (ROOT / "eval/eval_set.jsonl").read_text().splitlines()]
seen = defaultdict(int)
for it in items:
    it["split"] = "dev" if seen[it["category"]] % 2 == 0 else "test"
    seen[it["category"]] += 1
dev = [i for i in items if i["split"] == "dev"]
test = [i for i in items if i["split"] == "test"]


def correct(it, pred: Prediction) -> bool:
    exp = set(it["expected_intents"])
    if it["category"] == "state":
        return pred.mode == it["expected_mode"]
    if it["category"] == "unrouted":
        return not pred.intents
    return set(pred.intents) == exp


def score(results):
    cats = defaultdict(list)
    for it, pred, ok in results:
        cats[it["category"]].append(ok)
    row = {c: round(sum(v) / len(v) * 100) for c, v in cats.items()}
    row["macro"] = round(statistics.mean(row.values()))
    lat = [p.latency_ms for _, p, _ in results if p.latency_ms]
    row["p50_ms"] = round(statistics.median(lat)) if lat else 0
    row["p95_ms"] = round(sorted(lat)[int(len(lat) * 0.95)]) if lat else 0
    return row


def with_state(it, fn):
    st = turn_state(it["text"], it["prior"], it["state"])
    return st if st else fn()


table = {}          # name -> (row, results, extra)

# ---------------------------------------------------------------- rules
rules = RulesClassifier(reg)
res = [(it, p, correct(it, p)) for it in test for p in [with_state(it, lambda: rules(it["text"], it["prior"], it["state"]))]]
table["rules"] = (score(res), res, "")

# ---------------------------------------------------------------- embedding
emb = None
if args.emb:
    emb = EmbeddingClassifier(reg, args.emb)
    ecache = {}
    for it in items:
        t0 = time.perf_counter()
        ecache[it["id"]] = (emb.scores(it["text"]), (time.perf_counter() - t0) * 1000)

    def emb_pred(it):
        per, ms = ecache[it["id"]]
        hits = emb.decide(dict(per), it["prior"])
        return Prediction(hits, _mode(hits, it["prior"]), max(per.values()), ms)

    best = None
    for thr, margin, boost in itertools.product([0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75], [0.02, 0.04, 0.06, 0.08, 0.12, 0.2], [0.0, 0.05, 0.10, 0.20]):
        emb.thr, emb.margin, emb.prior_boost = thr, margin, boost
        acc = statistics.mean(correct(it, with_state(it, lambda: emb_pred(it))) for it in dev)
        if best is None or acc > best[0]:
            best = (acc, thr, margin, boost)
    emb.thr, emb.margin, emb.prior_boost = best[1:]
    res = [(it, p, correct(it, p)) for it in test for p in [with_state(it, lambda: emb_pred(it))]]
    table["embedding(0.6B)"] = (score(res), res, f"thr={best[1]} margin={best[2]} prior_boost={best[3]} (dev acc {best[0]:.2f})")

# ---------------------------------------------------------------- LLMs (cache every prediction once), then hybrids
for spec in args.llm:
    name, url = spec.split("=", 1)
    llm = LLMClassifier(reg, url, name, key=args.llm_key, fewshot=name.endswith("+fs"))
    lcache = {}
    for it in items:
        if not (it["state"].get("busy") or it["state"].get("pending_confirmation")):
            lcache[it["id"]] = llm(it["text"], it["prior"], it["state"])

    def llm_pred(it):
        return lcache[it["id"]]

    res = [(it, p, correct(it, p)) for it in test for p in [with_state(it, lambda: llm_pred(it))]]
    table[f"llm({name})"] = (score(res), res, "")

    if emb:
        def hyb(it, hi, gap):
            per, ems = ecache[it["id"]]
            r = sorted(per.values(), reverse=True)
            if r[0] >= hi and (r[0] - r[1]) >= gap and not it["prior"]:
                b = max(per, key=per.get)
                return Prediction([b], _mode([b], it["prior"]), r[0], ems, {"path": "emb"})
            lp = llm_pred(it)
            return Prediction(lp.intents, lp.mode, lp.top_score, ems + lp.latency_ms, {"path": "llm"})

        hbest = None
        for hi, gap in itertools.product([0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90], [0.0, 0.04, 0.08, 0.12]):
            acc = statistics.mean(correct(it, with_state(it, lambda: hyb(it, hi, gap))) for it in dev)
            llm_rate = statistics.mean((hyb(it, hi, gap).detail.get("path") == "llm") for it in dev if not it["state"].get("busy") and not it["state"].get("pending_confirmation"))
            key = (acc, -llm_rate)                         # accuracy first, then fewer LLM calls
            if hbest is None or key > hbest[0]:
                hbest = (key, hi, gap)
        _, hi, gap = hbest
        res = [(it, p, correct(it, p)) for it in test for p in [with_state(it, lambda: hyb(it, hi, gap))]]
        used = [p for _, p, _ in res if p.detail.get("path")]
        rate = round(sum(p.detail["path"] == "llm" for p in used) / max(1, len(used)) * 100)
        table[f"hybrid(emb→{name})"] = (score(res), res, f"hi={hi} gap={gap}; LLM used on {rate}% of messages")

# ---------------------------------------------------------------- report
print(f"\nTEST split: {len(test)} items (dev {len(dev)} used only for calibration)")
cats = ["standalone", "cross", "unrouted", "followup", "state"]
print(f"{'classifier':26s} " + " ".join(f"{c:>10s}" for c in cats) + "   macro   p50ms  p95ms")
for name, (row, _, extra) in table.items():
    print(f"{name:26s} " + " ".join(f"{str(row.get(c, '-')) + '%':>10s}" for c in cats) + f"   {row['macro']:4d}%  {row['p50_ms']:5d}  {row['p95_ms']:5d}")
print()
for name, (_, _, extra) in table.items():
    if extra:
        print(f"  {name}: {extra}")
print("\nMISSES (first 5 per classifier):")
for name, (_, res, _) in table.items():
    for it, p, ok in [(a, b, c) for a, b, c in res if not c][:5]:
        print(f"  [{name}] {it['category']:10s} '{it['text'][:46]}' expected={it['expected_intents']} got={p.intents}")

out = ROOT.parent / "runtime/results"
out.mkdir(parents=True, exist_ok=True)
json.dump({n: {"summary": r[0], "note": r[2], "per_item": [{"id": it["id"], "ok": ok, "pred": p.intents, "mode": p.mode, "ms": round(p.latency_ms)} for it, p, ok in r[1]]}
           for n, r in table.items()}, open(out / f"bench_{int(time.time())}.json", "w"), indent=1)
