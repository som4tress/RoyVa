"""Decide how a message is handled: steer / confirmation / new intent / continuation / fallback.
Classifiers form an ordered chain with a circuit breaker; if none can route the message the router raises RouterUnavailable (fail closed)."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .classifiers import CONFIRM, Prediction
from .models import AskRequest, SessionState


class RouterUnavailable(Exception):
    """No classifier in the chain could route this message."""


@dataclass
class Decision:
    mode: str                                   # new | continuation | steer | confirmation | fallback
    intents: list[str] = field(default_factory=list)
    classifier: str = "deterministic"
    latency_ms: int = 0
    confidence: float = 1.0
    degraded: bool = False                      # routed by a last-resort classifier


@dataclass
class Entry:
    name: str
    fn: Callable                                # sync callable(text, prior, state) -> Prediction; run in a worker thread
    degraded: bool = False                      # last-resort quality: an empty answer from it means "unavailable", not "no intent"
    fails: int = 0
    open_until: float = 0.0


class Router:
    """Backward compatible: Router(classifier, "name") builds a one-entry chain."""

    def __init__(self, classifier=None, name: str = "classifier", chain: Optional[list[Entry]] = None,
                 clock: Callable[[], float] = time.monotonic, breaker_threshold: int = 2, breaker_cooldown_s: float = 30.0):
        self.chain = chain if chain is not None else [Entry(name, classifier)]
        self.name = self.chain[0].name
        self.clock, self.threshold, self.cooldown = clock, breaker_threshold, breaker_cooldown_s

    def health(self) -> list[dict]:
        now = self.clock()
        def circuit(e: Entry) -> str:
            if e.open_until > now:
                return "open"                                  # being skipped
            return "half-open" if e.fails >= self.threshold else "closed"   # cooldown over: the next message retries it
        return [{"name": e.name, "degraded_tier": e.degraded, "consecutive_failures": e.fails, "circuit": circuit(e)} for e in self.chain]

    def rebuild(self, reg) -> None:
        """The registry changed: classifiers that embed intent descriptions in their prompt must refresh."""
        for e in self.chain:
            target = getattr(e.fn, "rebuild", None)
            if callable(target):
                target(reg)

    def _ok(self, e: Entry) -> None:
        e.fails, e.open_until = 0, 0.0

    def _bad(self, e: Entry) -> None:
        e.fails += 1
        if e.fails >= self.threshold:
            e.open_until = self.clock() + self.cooldown

    async def decide(self, req: AskRequest, state: Optional[SessionState]) -> Decision:
        if state and state.busy:
            return Decision("steer")
        if state and state.pending_confirmation and CONFIRM.match(req.text) and len(req.text) <= 40:
            return Decision("confirmation")
        prior = {"text": state.last_text, "intents": state.last_intents} if (state and state.last_text) else None
        tried = []
        for e in self.chain:
            if e.open_until > self.clock():
                tried.append(f"{e.name}: circuit open")
                continue
            t0 = time.perf_counter()
            try:
                pred: Prediction = await asyncio.to_thread(e.fn, req.text, prior, {"busy": False, "pending_confirmation": False})
            except Exception as ex:                                  # noqa: BLE001
                self._bad(e)
                tried.append(f"{e.name}: {type(ex).__name__}")
                continue
            self._ok(e)
            ms = int((time.perf_counter() - t0) * 1000)
            if not pred.intents:
                if e.degraded:                                       # a keyword fallback finding nothing is not evidence of "no intent"
                    tried.append(f"{e.name}: no match")
                    continue
                return Decision("fallback", [], e.name, ms, 0.0)
            mode = "continuation" if prior and set(pred.intents) <= set(prior["intents"]) else "new"
            return Decision(mode, list(pred.intents), e.name, ms, 1.0, degraded=e.degraded)
        raise RouterUnavailable("; ".join(tried) or "no classifiers configured")
