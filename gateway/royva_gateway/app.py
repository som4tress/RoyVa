"""FastAPI front door for the gateway. Bind to localhost only."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException

from . import registry as registry_mod
from .classifiers import LLMClassifier, RulesClassifier
from pathlib import Path

from pydantic import BaseModel

from .config import Settings
from .directory import Directory, DirectoryError
from .gmail_enroll import Enroller
from .models import AskRequest, AskResponse
from .opencode_client import OpenCodeClient
from .router import Entry, Router
from .service import Gateway
from .sessions import SessionStore


def build_gateway(settings: Optional[Settings] = None) -> Gateway:
    s = settings or Settings()
    reg = registry_mod.load(s.registry_dir)
    chain = [Entry(s.router_name, LLMClassifier(reg, s.router_url, s.router_name, fewshot=s.router_name.endswith("+fs"), timeout=s.router_timeout_s)),
             Entry(s.router_fallback_name, LLMClassifier(reg, s.router_fallback_url, s.router_fallback_name, fewshot=s.router_fallback_name.endswith("+fs"),
                                                         timeout=s.router_timeout_s)),
             Entry("rules", RulesClassifier(reg), degraded=True)]
    oc = OpenCodeClient(s.opencode_url, s.opencode_password, s.opencode_dir)
    store = SessionStore(s.state_dir / "sessions.json")
    store.prune()
    return Gateway(s, reg, Router(chain=chain), oc, store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    gw = build_gateway()
    app.state.gw = gw
    app.state.dir = Directory(gw.s.users_file, gw.s.state_dir, Enroller(gw.s.state_dir), Path(__file__).resolve().parents[2] / "config" / "opencode.json")
    app.state.ready_task = asyncio.create_task(gw.watch_ready())
    yield
    app.state.ready_task.cancel()
    await gw.oc.aclose()


app = FastAPI(title="RoyVa gateway", lifespan=lifespan)


async def require_token(authorization: str = Header(default="")):
    """If ROYVA_GATEWAY_TOKEN is set, every /v1/* call must carry it (keeps other local processes from driving the assistant)."""
    token = app.state.gw.s.token
    if token and authorization != f"Bearer {token}":
        raise HTTPException(401, "missing or wrong gateway token")


@app.get("/healthz")
async def healthz():
    gw: Gateway = app.state.gw
    try:
        mcp = await gw.oc.mcp_status()
    except Exception as e:                                   # noqa: BLE001
        mcp = {"error": str(e)[:80]}
    return {"ready": gw.ready, "mcp": mcp, "active_intents": [i.id for i in gw.reg.active()],
            "router": gw.router.health(), "sessions": gw.store.count()}


@app.get("/v1/registry", dependencies=[Depends(require_token)])
async def registry_summary():
    gw: Gateway = app.state.gw
    return [{"id": i.id, "status": i.status, "tools": i.profile.tools, "write_policy": i.profile.write_policy} for i in gw.reg.intents.values()]


@app.post("/v1/ask", response_model=AskResponse, dependencies=[Depends(require_token)])
async def ask(req: AskRequest):
    gw: Gateway = app.state.gw
    if not gw.ready:
        raise HTTPException(503, "starting: OpenCode MCP servers are not connected yet")
    return await gw.ask(req)


@app.post("/v1/reload", dependencies=[Depends(require_token)])
async def reload_registry():
    """Re-read registry files and regenerate home context. An invalid registry is rejected (400) and the running one is kept."""
    gw: Gateway = app.state.gw
    try:
        return await gw.reload()
    except registry_mod.RegistryError as e:
        raise HTTPException(400, {"error": "registry invalid; keeping the running registry", "problems": e.problems})


@app.get("/v1/stats", dependencies=[Depends(require_token)])
async def stats():
    """Operational view built from the rolling trace file: outcomes, modes, intents, router latency, router health, unsupported-request demand."""
    return app.state.gw.stats()


@app.post("/v1/session", dependencies=[Depends(require_token)])
async def new_session():
    """Create a conversation with the base agent and no tools (the bridge calls this instead of creating its own session)."""
    gw: Gateway = app.state.gw
    if not gw.ready:
        raise HTTPException(503, "starting: OpenCode MCP servers are not connected yet")
    try:
        return {"session_id": await gw.new_session()}
    except Exception as e:                                           # noqa: BLE001
        raise HTTPException(502, f"assistant backend error: {type(e).__name__}")


@app.post("/v1/route", dependencies=[Depends(require_token)])
async def route(req: AskRequest):
    """Route a message and prepare its session (tool grants + context). Does NOT run the model; the caller runs the turn.
    Errors come back as {"kind": "error", "answer": ...} so the caller can show the user a clear message."""
    gw: Gateway = app.state.gw
    if not gw.ready:
        raise HTTPException(503, "starting: OpenCode MCP servers are not connected yet")
    return await gw.route_for_bridge(req)


# ---- enrollment (who may use RoyVa). The bridge forwards Telegram commands here; the gateway is the only writer of users.json. ----
class Enroll(BaseModel):
    user: str                      # "telegram:<id>" of the person who sent the command (identity comes from Telegram, never from message text)
    name: str = ""
    gmail: str = ""
    code: str = ""
    display: str = ""
    text: str = ""
    approve: bool = True
    manage: bool = False


def _enroll_call(fn):
    try:
        return {"ok": True, **fn()}
    except DirectoryError as e:
        return {"ok": False, "error": str(e)}


@app.get("/v1/enroll/allowed", dependencies=[Depends(require_token)])
async def enroll_allowed():
    d: Directory = app.state.dir
    return {"ids": d.active_ids(), "owners": d.owner_ids()}


@app.post("/v1/enroll/invite", dependencies=[Depends(require_token)])
async def enroll_invite(r: Enroll):
    d: Directory = app.state.dir
    return _enroll_call(lambda: d.invite(r.user, r.name, r.gmail or None))


@app.post("/v1/enroll/join", dependencies=[Depends(require_token)])
async def enroll_join(r: Enroll):
    d: Directory = app.state.dir
    return _enroll_call(lambda: {**d.join(r.user, r.display, r.code), "owners": d.owner_ids()})


@app.post("/v1/enroll/decide", dependencies=[Depends(require_token)])
async def enroll_decide(r: Enroll):
    d: Directory = app.state.dir
    return _enroll_call(lambda: d.decide(r.user, r.name, r.approve))


@app.post("/v1/enroll/people", dependencies=[Depends(require_token)])
async def enroll_people(r: Enroll):
    d: Directory = app.state.dir
    return _enroll_call(lambda: {"people": d.people(r.user)})


@app.post("/v1/enroll/revoke", dependencies=[Depends(require_token)])
async def enroll_revoke(r: Enroll):
    d: Directory = app.state.dir
    return _enroll_call(lambda: d.revoke(r.user, r.name))


@app.post("/v1/enroll/gmail/start", dependencies=[Depends(require_token)])
async def enroll_gmail_start(r: Enroll):
    d: Directory = app.state.dir
    return _enroll_call(lambda: {"url": d.gmail_start(r.user, r.manage)})


@app.post("/v1/enroll/gmail/finish", dependencies=[Depends(require_token)])
async def enroll_gmail_finish(r: Enroll):
    """The pasted sign-in text goes only here: it is never logged and never reaches the model."""
    d: Directory = app.state.dir
    return _enroll_call(lambda: d.gmail_finish(r.user, r.text))


@app.post("/v1/enroll/gmail/stop", dependencies=[Depends(require_token)])
async def enroll_gmail_stop(r: Enroll):
    d: Directory = app.state.dir
    return _enroll_call(lambda: d.gmail_stop(r.user))


@app.post("/v1/admin/restart-opencode", dependencies=[Depends(require_token)])
async def restart_opencode():
    """Restart OpenCode so it loads newly connected Gmail servers. The caller waits until no run is active; the supervisor (systemd) restarts the process."""
    import subprocess
    from urllib.parse import urlparse
    gw: Gateway = app.state.gw
    pattern = gw.s.opencode_restart.format(port=urlparse(gw.s.opencode_url).port)
    subprocess.run(["pkill", "-f", pattern], check=False)
    return {"ok": True}


@app.post("/v1/enroll/is-signin", dependencies=[Depends(require_token)])
async def enroll_is_signin(r: Enroll):
    d: Directory = app.state.dir
    return {"signin": d.looks_like_signin(r.text)}
