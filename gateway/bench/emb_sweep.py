"""Sanity-check embedding setup: does an end-of-text suffix / query instruction prefix change plain top-1 accuracy?"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from royva_gateway import registry
from royva_gateway.classifiers import EmbeddingClassifier
ROOT = Path(__file__).resolve().parent.parent
reg = registry.load(ROOT / "registry")
items = [json.loads(l) for l in (ROOT / "eval/eval_set.jsonl").read_text().splitlines() if '"category": "standalone"' in l]

class Variant(EmbeddingClassifier):
    def __init__(self, reg, url, use_prefix, suffix):
        self.suffix = suffix
        super().__init__(reg, url, use_prefix)
    def _embed(self, texts, query):
        texts = [t + self.suffix for t in texts]
        return super()._embed(texts, query)

for use_prefix in (True, False):
    for suffix in ("", "<|endoftext|>"):
        c = Variant(reg, "http://127.0.0.1:8201", use_prefix, suffix)
        hit = 0
        for it in items:
            per = c.scores(it["text"])
            hit += max(per, key=per.get) == it["expected_intents"][0]
        print(f"prefix={str(use_prefix):5s} eos_suffix={'yes' if suffix else 'no ':3s}  top-1 on {len(items)} standalone items: {hit/len(items)*100:.0f}%")
