"""Classifier candidates for the router. Each takes (text, prior, state) and returns Prediction(intents, mode, score, latency_ms).
Deterministic turn-state handling (confirmations, steers) is NOT a classifier: it is plain code in `turn_state`."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
import numpy as np

from .registry import Registry

CONFIRM = re.compile(r"^\s*(yes|yep|yeah|sure|ok|okay|do it|go ahead|please do|confirm(ed)?|no|nope|cancel( that)?|stop|don'?t)\b[\s\w,!.']*$", re.I)


@dataclass
class Prediction:
    intents: list[str]
    mode: str                      # new | continuation | steer | confirmation | fallback
    top_score: float = 0.0
    latency_ms: float = 0.0
    detail: dict = field(default_factory=dict)


def turn_state(text: str, prior: Optional[dict], state: dict) -> Optional[Prediction]:
    """Rule-based handling of replies that must never be classified as new intents."""
    if state.get("busy"):
        return Prediction([], "steer")
    if state.get("pending_confirmation") and CONFIRM.match(text) and len(text) <= 40:
        return Prediction([], "confirmation")
    return None


def _mode(pred_intents: list[str], prior: Optional[dict]) -> str:
    if not pred_intents:
        return "fallback"
    if prior and set(pred_intents) <= set(prior["intents"]):
        return "continuation"
    return "new"


# ------------------------------------------------------------------------------------------ rules
KEYWORDS = {
    "home_state": [r"\b(status|is the .* (on|off|open|closed|locked)|are any|which .* (open|on))\b", r"\b(thermostat|humidity|temperature)\b"],
    "home_control": [r"\b(turn (on|off|up|down)|switch (on|off)|dim|lock|unlock|set the|close the|open the)\b"],
    "mail_read": [r"\b(emails?|inbox|gmail|unread)\b"],
    "web_lookup": [r"\b(forecast|weather|news|score|traffic|price of|who is|capital of|open on)\b"],
    "media_playback": [r"\b(play|pause|skip|volume|speaker|sonos|playlist|radio|music|announce)\b"],
    "tracking": [r"\b(alert me|notify me|track|watch|price alert|let me know if)\b"],
    "calendar": [r"\b(calendar|schedule|appointment|meeting|reschedule)\b"],
    "ha_automation": [r"\b(automation|automatically|routine|scene|every day at)\b"],
    "home_history": [r"\b(yesterday|last night|this week|last week|how many times|how long was|trend|overnight)\b"],
}


class RulesClassifier:
    name = "rules"

    def __init__(self, reg: Registry):
        self.rx = {k: [re.compile(p, re.I) for p in v] for k, v in KEYWORDS.items()}

    def __call__(self, text, prior, state) -> Prediction:
        t0 = time.perf_counter()
        hits = [k for k, pats in self.rx.items() if any(p.search(text) for p in pats)]
        if not hits and prior:
            hits = list(prior["intents"])                     # follow-up: inherit
        return Prediction(hits, _mode(hits, prior), 1.0 if hits else 0.0, (time.perf_counter() - t0) * 1000)


# ------------------------------------------------------------------------------------------ embeddings
class EmbeddingClassifier:
    """k-nearest-example. Intent score = max cosine to any of its examples/continuations. Thresholds are tuned on the dev split."""
    name = "embedding"
    TASK = "Instruct: Classify the user's request into the kind of household assistant task it is\nQuery: "

    def __init__(self, reg: Registry, url: str, use_prefix: bool = False):   # sweep: prefix hurt (70% vs 87% top-1)
        self.url, self.use_prefix = url.rstrip("/"), use_prefix
        self.http = httpx.Client(timeout=60)
        self.labels, texts = [], []
        for i in reg.intents.values():
            for s in i.examples + i.continuations:
                self.labels.append(i.id)
                texts.append(s)
        self.mat = self._embed(texts, query=False)
        self.thr, self.margin, self.prior_boost = 0.45, 0.06, 0.0   # defaults; calibrate() overrides

    def _embed(self, texts: list[str], query: bool) -> np.ndarray:
        inp = [(self.TASK + t) if (query and self.use_prefix) else t for t in texts]
        out = []
        for k in range(0, len(inp), 32):
            r = self.http.post(f"{self.url}/v1/embeddings", json={"input": inp[k:k + 32], "model": "emb"})
            r.raise_for_status()
            out += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
        m = np.array(out, dtype=np.float32)
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    def scores(self, text: str) -> dict[str, float]:
        v = self._embed([text], query=True)[0]
        sims = self.mat @ v
        per: dict[str, float] = {}
        for lab, s in zip(self.labels, sims):
            per[lab] = max(per.get(lab, -1.0), float(s))
        return per

    def decide(self, per: dict[str, float], prior) -> list[str]:
        ranked = sorted(per.items(), key=lambda kv: -kv[1])
        best_i, best_s = ranked[0]
        if prior:                                           # reward staying on the previous intent
            for k in prior["intents"]:
                per[k] = per.get(k, 0) + self.prior_boost
            ranked = sorted(per.items(), key=lambda kv: -kv[1])
            best_i, best_s = ranked[0]
        if best_s < self.thr:
            return []
        return [k for k, s in ranked if s >= self.thr and best_s - s <= self.margin][:2]

    def __call__(self, text, prior, state) -> Prediction:
        t0 = time.perf_counter()
        per = self.scores(text)
        hits = self.decide(dict(per), prior)
        top = max(per.values())
        return Prediction(hits, _mode(hits, prior), top, (time.perf_counter() - t0) * 1000)


# ------------------------------------------------------------------------------------------ LLM, constrained JSON
MAX_ROUTER_CHARS = 2000      # a pasted wall of text must never overflow the router's per-slot context; the ends carry the intent


def clip(text: str, limit: int) -> str:
    text = str(text)
    if len(text) <= limit:
        return text
    head = int(limit * 0.65)
    return text[:head] + " ... " + text[-(limit - head):]


class LLMClassifier:
    """A chat model asked to choose intent ids from the registry, with JSON-schema-constrained output.
    `rebuild(reg)` refreshes the prompt after a registry reload. Few-shot examples come from the registry (intent examples + router_examples.json)."""

    def __init__(self, reg: Registry, url: str, name: str, key: str = "", model: str = "x", fewshot: bool = False, timeout: float = 15.0):
        self.name, self.url, self.key, self.model, self.fewshot = name, url.rstrip("/"), key, model, fewshot
        self.http = httpx.Client(timeout=timeout)
        self.rebuild(reg)

    def rebuild(self, reg: Registry) -> None:
        self.ids = [i.id for i in reg.intents.values()]
        desc = "\n".join(f"- {i.id}: {i.description}" for i in reg.intents.values())
        system = (
            "You route messages for a household assistant. Choose which kinds of request the user's latest message needs.\n"
            f"Kinds:\n{desc}\n\n"
            "Rules: pick every kind needed (usually one, sometimes two). If the message is a short follow-up, use the previous "
            "request to decide. A message that asks for two different things needs BOTH kinds. "
            "If no kind fits (chit-chat, or a task none of the kinds covers), return an empty list.")
        if self.fewshot:
            shots = [f'"{ex}" -> {json.dumps([i.id])}' for i in reg.intents.values() for ex in i.examples[:3]]
            shots += [f'"{c["text"]}" -> {json.dumps(c["intents"])}' for c in reg.router_examples.get("cross", [])]
            shots += [f'"{t}" -> []' for t in reg.router_examples.get("none", [])]
            system += "\n\nExamples:\n" + "\n".join(shots)
        self.system = system
        self.schema = {"type": "object", "additionalProperties": False, "required": ["intents"],
                       "properties": {"intents": {"type": "array", "maxItems": 2, "items": {"type": "string", "enum": self.ids}}}}

    def __call__(self, text, prior, state) -> Prediction:
        user = (f"Previous request: {clip(prior['text'], 400)}\n" if prior else "") + f"Latest message: {clip(text, MAX_ROUTER_CHARS)}"
        body = {"model": self.model, "temperature": 0, "max_tokens": 60,
                "messages": [{"role": "system", "content": self.system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "route", "strict": True, "schema": self.schema}},
                "chat_template_kwargs": {"enable_thinking": False}}
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        t0 = time.perf_counter()
        r = self.http.post(f"{self.url}/v1/chat/completions", json=body, headers=headers)
        ms = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        # A reply that is not the expected JSON is a classifier FAILURE (the router chain moves on), never a silent "no intent".
        parsed = json.loads(r.json()["choices"][0]["message"]["content"])
        intents = parsed["intents"]
        if not isinstance(intents, list):
            raise ValueError("router reply has no intents list")
        hits = [i for i in intents if i in self.ids]
        return Prediction(hits, _mode(hits, prior), 1.0 if hits else 0.0, ms)


# ------------------------------------------------------------------------------------------ hybrid
class HybridClassifier:
    """Fast path: embedding when it is confident (top score >= `hi` and a clear winner). Otherwise ask the LLM."""
    def __init__(self, emb: EmbeddingClassifier, llm: LLMClassifier, hi: float = 0.70, gap: float = 0.08):
        self.emb, self.llm, self.hi, self.gap = emb, llm, hi, gap
        self.name = f"hybrid(emb→{llm.name})"
        self.llm_calls = 0
        self.calls = 0

    def __call__(self, text, prior, state) -> Prediction:
        t0 = time.perf_counter()
        per = self.emb.scores(text)
        ranked = sorted(per.values(), reverse=True)
        confident = ranked[0] >= self.hi and (ranked[0] - ranked[1]) >= self.gap and not prior
        self.calls += 1
        if confident:
            best = max(per, key=per.get)
            return Prediction([best], _mode([best], prior), ranked[0], (time.perf_counter() - t0) * 1000, {"path": "emb"})
        self.llm_calls += 1
        p = self.llm(text, prior, state)
        p.latency_ms += (time.perf_counter() - t0) * 1000 - p.latency_ms
        p.detail["path"] = "llm"
        return p
