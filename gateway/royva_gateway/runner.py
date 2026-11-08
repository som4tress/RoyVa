"""Run one user turn in an OpenCode session: send the prompt, poll until idle, enforce the tool-call budget (loop guard)."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

WRAP_UP = ("Stop calling tools now. Using only what you already have, answer the user's request. "
           "Say plainly what you could not complete or verify.")
NON_TOOL_PARTS = {"text", "reasoning", "thinking", "step-start", "step-finish"}


@dataclass
class TurnResult:
    answer: str
    tool_calls: int
    wrapped: bool = False
    timed_out: bool = False
    error: Optional[str] = None


def count_tool_calls(rows: list[dict]) -> int:
    n = 0
    for m in rows:
        if m.get("type") != "assistant":
            continue
        for p in m.get("content") or []:
            if p.get("type") and p["type"] not in NON_TOOL_PARTS:
                n += 1
    return n


def count_rounds(rows: list[dict]) -> int:
    """A round = one assistant message that issued tool calls (OpenCode records one assistant message per model step;
    parallel tool calls live inside it). The guard limits rounds, because a wide parallel fan-out (e.g. every area on a floor) is legitimate."""
    return sum(1 for m in rows if m.get("type") == "assistant"
               and any(p.get("type") and p["type"] not in NON_TOOL_PARTS for p in (m.get("content") or [])))


CALLS_PER_ROUND_CEILING = 6      # hard ceiling on total tool calls = cap * this (second safety net)


def last_answer(rows: list[dict]) -> tuple[str, Optional[Any]]:
    assistants = [m for m in rows if m.get("type") == "assistant"]
    if not assistants:
        return "", None
    last = assistants[-1]
    text = "\n\n".join(p.get("text", "") for p in (last.get("content") or []) if p.get("type") == "text").strip()
    return text, last.get("error")


def is_idle_after(session: dict, user_msg: dict) -> bool:
    t = session.get("time") or {}
    idle = t.get("idle")
    return idle is not None and idle >= user_msg["time"]["created"] and idle >= (t.get("busy") or 0)


async def run_turn(oc, sid: str, text: str, cap: int, *, timeout_s: float = 300, poll_s: float = 0.5,
                   sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, clock: Callable[[], float] = time.monotonic) -> TurnResult:
    known = {m["id"] for m in await oc.messages(sid)}
    await oc.prompt(sid, text, "queue")
    deadline = clock() + timeout_s
    wrapped = False
    calls = 0
    while clock() < deadline:
        await sleep(poll_s)
        msgs = await oc.messages(sid)
        rows = sorted((m for m in msgs if m["id"] not in known), key=lambda m: m["time"]["created"])
        calls = count_tool_calls(rows)
        rounds = count_rounds(rows)
        session = await oc.session(sid)
        if (rounds > cap or calls > cap * CALLS_PER_ROUND_CEILING) and not wrapped:
            # Budget exceeded: stop the run, then ask for an answer from what has been gathered.
            await oc.interrupt(sid)
            wrapped = True
            for _ in range(20):
                await sleep(poll_s)
                s2 = await oc.session(sid)
                t = s2.get("time") or {}
                if t.get("idle") is not None and t["idle"] >= (t.get("busy") or 0):
                    break
            await oc.prompt(sid, WRAP_UP, "queue")
            continue
        users = [m for m in rows if m.get("type") == "user"]
        if users and is_idle_after(session, users[-1]):
            answer, err = last_answer(rows)
            if err:
                return TurnResult(answer, calls, wrapped, error=str(err))
            return TurnResult(answer or "I finished without a text reply.", calls, wrapped)
    try:
        await oc.interrupt(sid)
    except Exception:                                        # noqa: BLE001
        pass
    return TurnResult("That took too long, so I stopped. Reply to continue.", calls, wrapped, timed_out=True)
