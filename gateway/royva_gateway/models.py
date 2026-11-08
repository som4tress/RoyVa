"""Contracts (API messages) and schemas (stored data) for the RoyVa gateway. Strict on purpose: unknown fields are rejected,
so a malformed or unsafe intent fails at load time instead of misbehaving at run time."""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SNAKE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
Risk = Literal["read", "write", "external"]            # external = leaves the house (send email, broadcast, spend money)
WritePolicy = Literal["read_only", "confirm", "auto"]
IntentStatus = Literal["planned", "candidate", "active", "retired"]
ContextProvider = Literal["home_map", "home_location", "current_location", "current_time", "speakers", "user_profile"]
CONTEXT_PROVIDERS: tuple[str, ...] = ("home_map", "home_location", "current_location", "current_time", "speakers", "user_profile")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- tool catalog (human-owned; the agent may not edit risk labels)
class ToolSpec(Strict):
    id: str                         # friendly id used in registry files, e.g. "ha.get_live_context"
    action: str                     # OpenCode permission/tool name, e.g. "home-assistant_homeassistant__GetLiveContext"
    server: str
    risk: Risk
    description: str
    available: bool = True          # False = planned tool, not built yet

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$", v):
            raise ValueError("tool id must look like 'server.tool_name'")
        return v


# ---------------------------------------------------------------- intents (the registry)
class Profile(Strict):
    tools: list[str] = Field(default_factory=list)          # catalog ids
    context: list[ContextProvider] = Field(default_factory=list)
    steps: int = Field(8, ge=1, le=20)                       # per-turn cap on model steps (the loop guard)
    write_policy: WritePolicy = "read_only"
    sticky: bool = True                                       # tools persist for the rest of the session
    scope: str = ""                                           # privacy scope (e.g. "email"): only users granted this scope may use the intent
    style: str = ""                                           # how to answer (concise, grouped...), added to the prompt for this intent


class Provenance(Strict):
    created_by: Literal["human", "agent"] = "human"
    version: int = Field(1, ge=1)
    approved_by: Optional[str] = None
    source_traces: list[str] = Field(default_factory=list)


class IntentStats(Strict):
    routed: int = 0
    succeeded: int = 0
    corrected: int = 0


class Intent(Strict):
    id: str
    status: IntentStatus
    description: str = Field(min_length=10)
    examples: list[str] = Field(min_length=5)
    negatives: list[str] = Field(min_length=2)
    continuations: list[str] = Field(default_factory=list)   # follow-up phrasings that keep this intent in a session
    profile: Profile
    provenance: Provenance = Field(default_factory=Provenance)
    stats: IntentStats = Field(default_factory=IntentStats)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not SNAKE.match(v):
            raise ValueError("intent id must be snake_case")
        return v

    @field_validator("examples", "negatives", "continuations")
    @classmethod
    def _nonblank_unique(cls, v: list[str]) -> list[str]:
        cleaned = [s.strip() for s in v]
        if any(not s for s in cleaned):
            raise ValueError("blank phrase")
        if len({s.lower() for s in cleaned}) != len(cleaned):
            raise ValueError("duplicate phrase")
        return cleaned

    @model_validator(mode="after")
    def _overlap(self) -> "Intent":
        overlap = {s.lower() for s in self.examples} & {s.lower() for s in self.negatives}
        if overlap:
            raise ValueError(f"example is also listed as a negative: {sorted(overlap)[:2]}")
        return self


# ---------------------------------------------------------------- API contract: bridge -> gateway
class AskRequest(Strict):
    text: str = Field(min_length=1, max_length=8000)
    user: str                                  # e.g. "telegram:123456"
    session_id: Optional[str] = None            # None = new session
    is_reply: bool = False

    @model_validator(mode="after")
    def _reply_needs_session(self) -> "AskRequest":
        if self.is_reply and not self.session_id:
            raise ValueError("is_reply=true requires session_id")
        return self


RouteMode = Literal["new", "continuation", "steer", "confirmation", "fallback"]
AskStatus = Literal["done", "needs_confirmation", "busy_steered", "error"]


class RoutingInfo(Strict):
    trace_id: str
    mode: RouteMode
    intents: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    profile_tools: list[str]


class AskResponse(Strict):
    session_id: Optional[str]
    answer: str
    routing: RoutingInfo
    status: AskStatus


# ---------------------------------------------------------------- session state (gateway store)
class PendingConfirmation(Strict):
    action: str
    message_id: Optional[int] = None


class SessionState(Strict):
    session_id: str
    intents_seen: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)           # sticky union, only grows
    last_intent: Optional[str] = None
    last_intents: list[str] = Field(default_factory=list)
    last_text: Optional[str] = None
    grants: dict[str, str] = Field(default_factory=dict)      # tool id -> allow|ask currently granted in OpenCode
    contexts_sent: list[str] = Field(default_factory=list)   # context providers already included in this session
    pending_confirmation: Optional[PendingConfirmation] = None
    busy: bool = False
    turns: int = 0
    created_at: str
    updated_at: Optional[str] = None


# ---------------------------------------------------------------- routing trace (the unit for debugging and learning)
class Candidate(Strict):
    intent: str
    score: float


class RoutingTrace(Strict):
    trace_id: str
    session_id: str
    text: str
    mode: RouteMode
    candidates: list[Candidate]
    chosen: list[str]
    classifier: Literal["rules", "embedding", "llm", "fallback", "deterministic"]
    latency_ms: int
    outcome: Optional[Literal["ok", "corrected", "failed"]] = None
    capture_ids: list[str] = Field(default_factory=list)     # links to proxy captures
