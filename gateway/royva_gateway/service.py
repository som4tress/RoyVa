"""The gateway: route a message, prepare the OpenCode session (tool grants + context), optionally run the turn, remember the outcome.
`prepare` does routing + session setup and never runs the model; `ask` = prepare + run (self-contained path);
the Telegram bridge uses `prepare` (via /v1/route) and keeps running the turn itself, so its progress/steer/permission UX is untouched.
Failure policy: fail closed with a clear message; never leave a session marked busy; never crash the caller."""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from . import profiles, registry as registry_mod
from .config import Settings
from .models import AskRequest, AskResponse, RoutingInfo, SessionState
from .registry import Registry
from .router import Decision, Router, RouterUnavailable
from .runner import WRAP_UP, CALLS_PER_ROUND_CEILING, run_turn
from .sessions import SessionStore

MSG_ROUTER_DOWN = "I can't work out what you're asking right now because my routing models are unavailable. Please try again in a moment."
MSG_BACKEND_DOWN = "I couldn't set that up because the assistant backend returned an error. Please try again in a moment."
TRACE_MAX_BYTES = 20 * 1024 * 1024
TRACE_KEEP = 3


@dataclass
class Prepared:
    kind: str                                  # run | steer | answer | silent (send nothing)
    decision: Decision
    trace_id: str
    session_id: Optional[str] = None
    prompt: str = ""
    cap: int = 6
    tools: list[str] = field(default_factory=list)
    grants: dict = field(default_factory=dict)
    answer: str = ""                           # for kind == answer / steer
    state: Optional[SessionState] = None
    acting: list = field(default_factory=list)
    new_ctx: list[str] = field(default_factory=list)


class Gateway:
    def __init__(self, settings: Settings, reg: Registry, router: Router, oc, store: SessionStore):
        self.s, self.reg, self.router, self.oc, self.store = settings, reg, router, oc, store
        self.sem = asyncio.Semaphore(settings.max_concurrent_runs)
        self.ready = False
        self._loc_cache: dict = {}                            # person -> (monotonic ts, text or None)
        self._locks: dict[str, asyncio.Lock] = {}
        self.started = time.time()
        self.trace_path = settings.state_dir / "traces.jsonl"
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- readiness (bug B3: MCP tools appear only after servers connect)
    async def wait_ready(self, timeout: float = 180, poll: float = 2.0) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                st = await self.oc.mcp_status()
                if all(st.get(n) == "connected" for n in self.s.expected_mcp):
                    await self.refresh_context()
                    self.ready = True
                    return True
            except Exception:                                # noqa: BLE001
                pass
            await asyncio.sleep(poll)
        return False

    async def check_ready_once(self) -> bool:
        """Re-evaluate readiness from OpenCode's live MCP status. Going not-ready -> ready regenerates the Home Assistant context."""
        try:
            st = await self.oc.mcp_status()
            ok = all(st.get(n) == "connected" for n in self.s.expected_mcp)
        except Exception:                                    # noqa: BLE001
            ok = False
        if ok and not self.ready:
            await self.refresh_context()
            self._trace(trace_id="ctx", text="ready", outcome=None)
        if self.ready and not ok:
            self._trace(trace_id="ctx", text="not ready: OpenCode MCP servers disconnected", outcome=None)
        self.ready = ok
        return ok

    async def watch_ready(self, interval: float = 5.0) -> None:
        """Keep `ready` honest for the life of the process (OpenCode can restart underneath us; its MCP servers reconnect asynchronously)."""
        while True:
            await self.check_ready_once()
            await asyncio.sleep(interval)

    async def current_location_text(self, user: str) -> Optional[str]:
        """Per-message 'the user is away in <city>' line, from the user's HA person + geocoded sensor (city-level only). Cached briefly."""
        from . import home_context
        person = self.user_person(user)
        if not person:
            return None
        now = time.monotonic()
        hit = self._loc_cache.get(person)
        if hit and now - hit[0] < self.s.location_ttl_s:
            return hit[1]
        try:
            info = await asyncio.to_thread(home_context.person_place, person)
            text = home_context.away_text(info)
        except Exception:                                    # noqa: BLE001
            text = None
        self._loc_cache[person] = (now, text)
        return text

    async def refresh_context(self) -> dict:
        """(Re)generate home_map / home_location / household / speakers from Home Assistant. Failures keep the previous/static context."""
        from . import home_context
        try:
            place = self.s.home_location
            if not place and self.s.default_person:          # derive a city-level home place from HA when the user is home
                info = await asyncio.to_thread(home_context.person_place, self.s.default_person)
                if info.get("at_home") and info.get("city"):
                    place = ", ".join(x for x in (info["city"], info.get("region")) if x)
            ctx = await asyncio.to_thread(home_context.load, place, self.s.default_person)
            self.s.dynamic_context.update(ctx)
            return ctx
        except Exception as e:                               # noqa: BLE001
            self._trace(trace_id="ctx", text="refresh_context failed", error=str(e)[:120])
            return {}

    async def reload(self) -> dict:
        """Atomically re-read the registry (a bad registry is rejected and the old one kept), refresh classifiers' prompts and HA context."""
        new = await asyncio.to_thread(registry_mod.load, self.s.registry_dir)       # raises RegistryError, leaving self.reg untouched
        self.reg = new
        self.router.rebuild(new)
        ctx = await self.refresh_context()
        return {"intents": len(new.intents), "active": [i.id for i in new.active()], "context_refreshed": sorted(ctx)}

    # ---------------------------------------------------------------- tracing (rotating) and stats
    def _rotate(self) -> None:
        try:
            if self.trace_path.exists() and self.trace_path.stat().st_size > TRACE_MAX_BYTES:
                for n in range(TRACE_KEEP - 1, 0, -1):
                    src = self.trace_path.with_suffix(f".{n}.jsonl")
                    if src.exists():
                        os.replace(src, self.trace_path.with_suffix(f".{n + 1}.jsonl"))
                os.replace(self.trace_path, self.trace_path.with_suffix(".1.jsonl"))
        except OSError:
            pass

    def _trace(self, **rec) -> None:
        rec["ts"] = datetime.now(timezone.utc).isoformat()
        self._rotate()
        with open(self.trace_path, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def stats(self, window: int = 2000) -> dict:
        rows: list[dict] = []
        if self.trace_path.exists():
            with open(self.trace_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - 1_500_000))
                for line in f.read().decode("utf-8", "ignore").splitlines()[-window:]:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
        turns = [r for r in rows if r.get("outcome") and r.get("trace_id") not in ("ctx", "session")]
        lat = sorted(r["latency_ms"] for r in turns if isinstance(r.get("latency_ms"), (int, float)))
        missing = Counter(t for r in turns if r.get("outcome") == "unsupported" for t in (r.get("missing") or []))
        pct = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else None
        return {"uptime_s": int(time.time() - self.started), "ready": self.ready, "turns_in_window": len(turns),
                "outcomes": dict(Counter(r["outcome"] for r in turns)), "modes": dict(Counter(r.get("mode") for r in turns)),
                "intents": dict(Counter(i for r in turns for i in (r.get("chosen") or []))),
                "classifiers": dict(Counter(r.get("classifier") for r in turns)), "router_latency_ms": {"p50": pct(0.5), "p95": pct(0.95)},
                "avg_tool_calls": round(statistics.mean([r["tool_calls"] for r in turns if isinstance(r.get("tool_calls"), int)] or [0]), 2),
                "unsupported_demand": dict(missing.most_common(10)), "router": self.router.health(), "sessions": self.store.count()}

    def _info(self, trace_id: str, d: Decision, tools: list[str]) -> RoutingInfo:
        return RoutingInfo(trace_id=trace_id, mode=d.mode, intents=d.intents, confidence=d.confidence, profile_tools=tools)

    def _lock(self, sid: Optional[str]) -> asyncio.Lock:
        if len(self._locks) > 5000:                           # drop idle locks
            self._locks = {k: v for k, v in self._locks.items() if v.locked()}
        return self._locks.setdefault(sid or "_new", asyncio.Lock())

    def _failure(self, req: AskRequest, message: str, why: str, trace_id: str) -> AskResponse:
        self._trace(trace_id=trace_id, session_id=req.session_id, text=req.text[:200], mode="fallback", chosen=[], outcome="error", error=why[:160])
        d = Decision("fallback", [], "error", 0, 0.0)
        return AskResponse(session_id=req.session_id, answer=message, status="error", routing=self._info(trace_id, d, []))

    # ---------------------------------------------------------------- per-user policy (privacy scopes)
    def _users(self) -> dict:
        """users file with a tiny mtime cache. A missing or corrupt file means nobody has private scopes (fail closed)."""
        path = self.s.users_file
        try:
            mtime = path.stat().st_mtime
            if getattr(self, "_users_cache", (None, None))[0] != mtime:
                self._users_cache = (mtime, json.loads(path.read_text()))
            return self._users_cache[1]
        except (OSError, ValueError):
            return {}

    def user_scopes(self, user: str) -> set:
        return set((self._users().get(user) or {}).get("scopes", []))

    def user_person(self, user: str) -> str:
        return (self._users().get(user) or {}).get("person") or self.s.default_person

    def silent_scopes(self) -> set:
        """Scopes whose refusals send NO reply at all (users file: {"_policy": {"silent_scopes": ["email"]}})."""
        return set((self._users().get("_policy") or {}).get("silent_scopes", []))

    def may_use(self, user: str, intent) -> bool:
        scope = intent.profile.scope
        if not scope:
            return True
        have = self.user_scopes(user)
        return "*" in have or scope in have

    # ---------------------------------------------------------------- sessions created for the bridge before routing
    async def new_session(self) -> str:
        """A conversation with the base agent and NO tools; /v1/route grants tools once the first message is routed."""
        perms = profiles.permissions(self.reg, {}, self.s)
        sid = await self.oc.create_session(self.s.agent, perms)
        self.store.put(SessionState(session_id=sid, created_at=datetime.now(timezone.utc).isoformat()))
        self._trace(trace_id="session", session_id=sid, text="new_session", mode="new", chosen=[])
        return sid

    # ---------------------------------------------------------------- prepare: route + set up the session (never runs the model)
    async def prepare(self, req: AskRequest) -> Prepared:
        trace_id = "rt_" + uuid.uuid4().hex[:10]
        state = self.store.get(req.session_id)
        if req.session_id and state is None:                  # a session created outside the gateway (e.g. before it existed)
            state = SessionState(session_id=req.session_id, created_at=datetime.now(timezone.utc).isoformat())
        d = await self.router.decide(req, state)

        if d.mode == "steer":
            self._trace(trace_id=trace_id, session_id=state.session_id, text=req.text[:200], mode="steer", chosen=[], outcome="steered")
            return Prepared("steer", d, trace_id, state.session_id, answer="Got it, adjusting the current request.", tools=state.tools, state=state)

        intents = [self.reg.intents[i] for i in d.intents if i in self.reg.intents]
        forbidden = [i for i in intents if i.status == "active" and not self.may_use(req.user, i)]
        acting = [i for i in intents if i.status == "active" and i not in forbidden]
        blocked = [i for i in intents if i.status != "active"]
        quiet = self.silent_scopes()
        unsupported = [f"{i.id.replace('_', ' ')} ({i.status})" for i in blocked] + [f"{i.profile.scope} access is limited to the account owner"
                                                                                  for i in forbidden if i.profile.scope not in quiet]
        if forbidden and not acting and not blocked:                  # fail closed: a user without the scope gets nothing run, and a refusal (or silence)
            scopes = sorted({i.profile.scope for i in forbidden})
            silent = all(sc in quiet for sc in scopes)
            self._trace(trace_id=trace_id, session_id=req.session_id, text=req.text[:200], mode=d.mode, chosen=d.intents,
                        outcome="forbidden_silent" if silent else "forbidden", scope=", ".join(scopes), classifier=d.classifier, latency_ms=d.latency_ms)
            return Prepared("silent" if silent else "answer", d, trace_id, req.session_id, state=state,
                            answer="" if silent else f"Sorry, {', '.join(scopes)} access is limited to the account owner, so I can't help with that here.")

        if d.mode == "confirmation":
            grant_map, hint, new_ctx, cap = dict(state.grants), "", [], 4
        else:
            if intents and not acting:
                need = sorted({t for i in blocked for t in i.profile.tools if not self.reg.tools[t].available})
                msg = ("I can't do that yet. It needs " + (", ".join(need) if need else "an intent that isn't enabled") +
                       ", which isn't available. I've noted that you asked for it.")
                self._trace(trace_id=trace_id, session_id=req.session_id, text=req.text[:200], mode=d.mode, chosen=d.intents, outcome="unsupported",
                            missing=need or d.intents, classifier=d.classifier, latency_ms=d.latency_ms)
                return Prepared("answer", d, trace_id, req.session_id, answer=msg, state=state)
            seen = [self.reg.intents[i] for i in (state.intents_seen if state else []) if i in self.reg.intents and self.reg.intents[i].status == "active"
                    and self.may_use(req.user, self.reg.intents[i])]          # earlier turns by someone else never lend their tools to this user
            session_intents = list({i.id: i for i in seen + acting}.values())        # tools are the union over the whole conversation, recomputed each turn
            grant_map = profiles.grants(self.reg, session_intents)
            have = set(state.contexts_sent) if state else set()
            new_ctx = list(dict.fromkeys(c for i in acting for c in i.profile.context if c not in have or c in profiles.PER_TURN_PROVIDERS))
            hint = profiles.capability_hint(self.reg, acting)
            cap = profiles.step_cap(acting)

        tools = list(grant_map)
        perms = profiles.permissions(self.reg, grant_map, self.s)
        known = self.store.get(req.session_id)
        now = datetime.now(timezone.utc).isoformat()
        if known is not None:                                  # a session the gateway already manages
            state = known
            if grant_map != state.grants:
                await self.oc.set_permissions(state.session_id, perms)
        elif req.session_id:                                   # created outside the gateway: adopt it and set its grants
            await self.oc.set_permissions(req.session_id, perms)
            state = SessionState(session_id=req.session_id, created_at=now)
        else:                                                  # brand-new conversation
            state = SessionState(session_id=await self.oc.create_session(self.s.agent, perms), created_at=now)

        per_turn = {"current_location": await self.current_location_text(req.user)} if "current_location" in new_ctx else {}
        text = profiles.prompt_text(req.text, new_ctx, hint, self.s, unsupported, per_turn, profiles.style_hint(acting), [i.id for i in acting])
        return Prepared("run", d, trace_id, state.session_id, prompt=text, cap=cap, tools=tools, grants=grant_map, state=state, acting=acting, new_ctx=new_ctx)

    def commit(self, p: Prepared, req: AskRequest, outcome: str = "prepared", tool_calls: Optional[int] = None) -> None:
        """Remember what this turn used so follow-ups inherit intents, tools and already-sent context."""
        state = p.state
        state.busy = False
        state.tools = p.tools
        state.grants = dict(p.grants)
        state.turns += 1
        state.last_text = req.text
        state.updated_at = datetime.now(timezone.utc).isoformat()
        if p.decision.mode != "confirmation":
            state.last_intents = [i.id for i in p.acting] or state.last_intents
            state.last_intent = state.last_intents[0] if state.last_intents else None
            state.intents_seen = list(dict.fromkeys(state.intents_seen + [i.id for i in p.acting]))
            state.contexts_sent = list(dict.fromkeys(state.contexts_sent + [c for c in p.new_ctx if c not in profiles.PER_TURN_PROVIDERS]))
        state.pending_confirmation = None
        self.store.put(state)
        self._trace(trace_id=p.trace_id, session_id=state.session_id, text=req.text[:200], mode=p.decision.mode, chosen=[i.id for i in p.acting],
                    classifier=p.decision.classifier, latency_ms=p.decision.latency_ms, tool_calls=tool_calls, outcome=outcome, tools=p.tools,
                    degraded=p.decision.degraded or None)

    # ---------------------------------------------------------------- self-contained path: prepare + run
    async def ask(self, req: AskRequest) -> AskResponse:
        trace_id = "rt_" + uuid.uuid4().hex[:10]
        try:
            async with self._lock(req.session_id):               # two messages racing into one session must not interleave their setup
                p = await self.prepare(req)
                if p.kind == "run":
                    p.state.busy = True
                    self.store.put(p.state)
        except RouterUnavailable as e:
            return self._failure(req, MSG_ROUTER_DOWN, f"router: {e}", trace_id)
        except Exception as e:                                   # noqa: BLE001  (OpenCode/HTTP/anything: contain it)
            return self._failure(req, MSG_BACKEND_DOWN, f"prepare: {type(e).__name__}: {e}", trace_id)

        if p.kind == "steer":
            try:
                await self.oc.prompt(p.session_id, req.text, "steer")
            except Exception as e:                               # noqa: BLE001
                return self._failure(req, MSG_BACKEND_DOWN, f"steer: {type(e).__name__}", p.trace_id)
            return AskResponse(session_id=p.session_id, answer=p.answer, status="busy_steered", routing=self._info(p.trace_id, p.decision, p.tools))
        if p.kind in ("answer", "silent"):
            return AskResponse(session_id=p.session_id, answer=p.answer, status="done", routing=self._info(p.trace_id, p.decision, []))

        res = None
        try:
            async with self.sem:
                res = await run_turn(self.oc, p.session_id, p.prompt, p.cap, timeout_s=self.s.run_timeout_s, poll_s=self.s.poll_interval_s)
        except Exception as e:                                   # noqa: BLE001
            p.state.busy = False
            self.store.put(p.state)                              # never leave a session persisted as busy
            return self._failure(req, MSG_BACKEND_DOWN, f"run: {type(e).__name__}: {e}", p.trace_id)
        finally:
            p.state.busy = False
        outcome = "error" if res.error else ("timeout" if res.timed_out else ("wrapped" if res.wrapped else "ok"))
        self.commit(p, req, outcome, res.tool_calls)
        return AskResponse(session_id=p.session_id, answer=res.answer, status="error" if res.error else "done",
                           routing=self._info(p.trace_id, p.decision, p.tools))

    # ---------------------------------------------------------------- bridge path: route only; the bridge runs the turn
    async def route_for_bridge(self, req: AskRequest) -> dict:
        trace_id = "rt_" + uuid.uuid4().hex[:10]
        try:
            async with self._lock(req.session_id):
                p = await self.prepare(req)
                if p.kind == "run":
                    self.commit(p, req)
        except RouterUnavailable as e:
            self._trace(trace_id=trace_id, session_id=req.session_id, text=req.text[:200], mode="fallback", chosen=[], outcome="error", error=f"router: {e}"[:160])
            return {"kind": "error", "session_id": req.session_id, "trace_id": trace_id, "answer": MSG_ROUTER_DOWN, "intents": [], "tools": []}
        except Exception as e:                                   # noqa: BLE001
            self._trace(trace_id=trace_id, session_id=req.session_id, text=req.text[:200], mode="fallback", chosen=[], outcome="error",
                        error=f"prepare: {type(e).__name__}: {e}"[:160])
            return {"kind": "error", "session_id": req.session_id, "trace_id": trace_id, "answer": MSG_BACKEND_DOWN, "intents": [], "tools": []}
        write_tools = {self.reg.tools[t].action: self.reg.tools[t].description for t in p.tools if t in self.reg.tools and self.reg.tools[t].risk != "read"}
        return {"kind": p.kind, "session_id": p.session_id, "trace_id": p.trace_id, "mode": p.decision.mode,
                "intents": p.decision.intents, "tools": p.tools, "cap": p.cap, "calls_ceiling": p.cap * CALLS_PER_ROUND_CEILING,
                "wrap_up": WRAP_UP, "answer": p.answer, "prompt": p.prompt,
                "write_tools": write_tools, "can_act": bool(write_tools)}              # the bridge builds the "what I did" report from these
