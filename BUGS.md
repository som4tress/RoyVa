# RoyVa bug log

Method: one bug at a time. Each entry cites a captured request ID (`captures/<id>.req.json`, `captures/index.jsonl`),
states expected vs actual, a hypothesis (not a confirmed cause until tested), the generic fix, and before/after numbers
from re-running the full six-prompt suite. A fix must help the suite as a whole, not one prompt.

Baseline stack: vanilla OpenCode v2.2.5 (binary hash matches inventory; build reproducibility vs upstream unverified),
Qwen3.6-35B-A3B Q8_0 on llama.cpp b12110 Vulkan, minimal config (no instructions, no plugins, HA + Gmail MCP only,
mutating tools denied), logging proxy, production Telegram bridge copy.

Status key: OPEN · HYPOTHESIS · FIXING · FIXED (with numbers) · WONTFIX

---

## B1 — Coding-agent system prompt for a household assistant   [OPEN]
- Evidence: capture `20261107232616-0002`: system prompt 2,130 tokens begins "You are an AI agent running in OpenCode, a
  coding agent harness", includes "Working in codebases" rules and a "Code Mode" JS catalog of OpenCode-management tools.
- Expected: short assistant-appropriate prompt. Actual: coding-harness prompt on every request.
- Hypothesis: it biases the model toward file exploration (see B2) and costs ~2.1k tokens per request.
- Candidate generic fix: replace/override the default system prompt via an agent profile or config option; measure.

## B2 — Model explores the filesystem before answering   [OPEN]
- Evidence: `…-0002`, `…-0003`: first two actions were `read` on the workspace dir then `/home/somdutta/RoyVa` for
  "What is the status of lights upstairs?". ~11 s of extra round-trips; 12 built-in tools (edit, write, shell, glob,
  grep, subagent, webfetch, websearch, skill, question, read, execute) are offered.
- Hypothesis: coding prompt + coding tools invite repo exploration.
- Candidate generic fix: remove/deny built-in coding tools for the assistant profile; verify deny hides them from the schema
  (deny rules did remove the 12 denied HA/Gmail tools from the schema — confirmed in `…-0003`: 19 tools, no mutators).

## B3 — MCP tools absent on the first model step   [OPEN — REPRODUCED 2026-11-08]
- Evidence: `…-0002` carried 12 tools and none of the HA/Gmail ones; from `…-0003` the 7 allowed MCP tools appear (19 total).
- Impact if real: the first message after a (re)start could not call HA at all, and an answer like "I don't have access"
  becomes likely (cf. the P2 refusals in the isolation harness).
- Reproduced: after restarting OpenCode, the very first request (session with HA grants) carried tools=['skill'] only; the same
  request on a warm instance carried the HA tools. Hypothesis stands: MCP servers connect asynchronously after startup.
- Fix path: `GET /api/mcp` reports per-server status (`connected`); the gateway waits for all expected servers before serving.

## B4 — Discovery thrash: floors/areas unknown to the model   [OPEN]
- Evidence: `…-0004`..`…-0006`: `GetLiveContext{area:"upstairs"}` → error "No exposed entities found in area 'upstairs'";
  then `{}` (9.9k-char full-home dump ≈ 3k tokens); then three per-area calls. 5 HA calls and 3 extra LLM round-trips.
  History grew 342 → 3,345 tokens. Final answer lists lights in Master Bedroom and Shivi Bedroom; whether those are
  exactly the "upstairs" lights has not been verified against the HA floor registry.
- Hypothesis: the model has no map of floors → areas, so "upstairs/downstairs/outside" has no direct lookup.
- Candidate generic fix: a compact, generated "home map" (floors → areas, with synonyms) supplied as context or a tool.

## B5 — Extra title-generation LLM call per session   [OPEN, low priority]
- Evidence: `…-0001`: 0 tools, 421-token system prompt, ~4.7 s. Runs once per new session (Telegram creates one per message).
- Candidate fix: configure a cheaper/no-op title path if OpenCode allows it; otherwise accept.

## B6 — Runaway tool loop with no budget ("oldest unread emails")   [OPEN — reproduced]
- Evidence: API-path run, prompt "List the top 20 oldest unread emails from my gmail." → 55 LLM requests, max prompt 97,885
  tokens, ≥223 s (captures `20261107233…`, see `index.jsonl`). Calls: `gmail_list_messages` ×2 (page 1–2 of INBOX+UNREAD,
  maxResults 100) then `gmail_search_messages` with ever-different date windows (`before:`, `older_than:`, `newer_than:`,
  `sort:date`) — none of which the Gmail search syntax supports as intended.
- Expected: either a correct "oldest first" result, or a bounded attempt that stops and says what it could not do.
- Hypothesis (two causes): (a) the Gmail tool returns newest-first and has no sort/"last page" support, so "oldest" requires
  paging to the end; (b) nothing caps tool-call count or detects "same tool, near-duplicate args".
- Candidate generic fixes: (1) a per-turn step/tool-call budget with forced wrap-up (applies to every prompt);
  (2) tool-level: `order=oldest` / count-aware paging helper. Do (1) first; (2) is Gmail-specific.

## B7 — Capability refusals without trying tools (P2, P3)   [OPEN — reproduced in OpenCode and in the isolation harness]
- Evidence: P2 "…mustang travelled this week?" → 1 request, 0 tool calls: "I don't have access to vehicle telematics or car
  data through the tools available to me." P3 "…forecast for the next 10 days?" → 1 request, 0 tool calls: "I don't have
  access to a weather tool … what city?" even though `websearch`/`webfetch` are in the tool list (capture `…-0002`).
  Isolation harness (180 runs) showed the same P2 refusal pattern, which a 2-sentence "tools cover X; search before
  refusing" prompt eliminated (47% → 100% first-tool-correct).
- Hypothesis: the model is not told what its tools cover (HA holds vehicle sensors; web tools answer weather) nor where
  "home" is (forecast location).
- Candidate generic fix: a small assistant context block: capabilities + home location + "look it up before saying you
  cannot". Same block should carry the home map from B4.

## B8 — `skill` tool leaks through `deny *`   [OPEN]
- Evidence: session with agent `royva` (deny *) and no grants still received tools=['skill'] (session_perm_test.mjs, C).
- Fix: explicit deny rule for `skill` in the base agent (and review other built-ins that ignore `*`).

## Design finding — per-session permissions (validated 2026-11-08)
- Session create accepts `{agent, permissions}`; PATCH /api/session/:id widens permissions mid-session; captured requests confirm the
  model receives exactly the granted tools (Gmail-only session -> 4 Gmail tools; PATCH added websearch/webfetch). So the gateway uses
  ONE base agent (deny *, short prompt) + per-session grants = union of the session's intents. No per-combination agents.

---
Template for new entries:

    ## Bn — title   [STATUS]
    - Evidence: capture IDs + one-line observation
    - Expected / Actual
    - Hypothesis (label as such) · Root cause (only once confirmed)
    - Fix (generic?) · Before/after: suite metrics


---
## Status as of 2026-11-08 (gateway hardening pass)
| Bug | Status | How / evidence |
|---|---|---|
| B1 coding-agent system prompt | FIXED | base agent `royva` has its own short prompt (system ~250 tokens vs ~2,130) |
| B2 filesystem exploration / coding tools | FIXED | base agent denies everything; per-session grants expose only the intent's tools; `never_grant` list |
| B3 MCP tools absent on first step | MITIGATED | gateway readiness is continuous (`watch_ready`): 503 until all MCP servers are connected, and again if OpenCode restarts (drill 3). The underlying OpenCode race remains. |
| B4 floor/area thrash | FIXED | home map generated from HA registries; upstairs now checks all areas; follow-up "and downstairs?" works in-session |
| B5 title-generation call per session | OPEN (low) | one extra ~0.5 s model call per new session; not yet suppressed |
| B6 runaway tool loop | FIXED | per-turn round cap (intent `steps`) with forced wrap-up; counts rounds not parallel calls (a fan-out of 8 areas is fine); regression tests |
| B7 capability refusals | MITIGATED | capability hint per intent + generated context; P2/P3 replay went 55%/10% -> ~100% first-tool-ok; Ford distance and forecast now answered |
| B8 `skill` leaking through deny * | FIXED | explicit deny in the base agent and in `never_grant` |

Hardening verified by failure injection (tests/test_hardening.py, 99 tests total) and live drills: router failover (9B -> 4B -> keyword rules) with circuit
breaker; fail-closed when no router works; OpenCode down -> 503 + friendly Telegram message + automatic recovery; invalid registry edits rejected on reload;
never leave a session persisted as busy; GET-only retries; token auth; trace rotation; session pruning; stats endpoint with unsupported-demand counter.

Regressions caught by the new tests during this pass (worth remembering): a rewrite of app.py silently deleted /v1/session and /v1/route (now pinned by a
route-table test); a style-hint test coupled to wording (now asserts the principle); loop guard once counted parallel calls (now rounds).

Known gaps: B5; write capabilities intentionally OFF (speakers/TTS, run-routine, automations, calendar, trackers, camera analysis); remote escalation and
recipe learning (phase 2); fresh held-out routing eval set needed (real_v1 is a tuning set); per-user mapping beyond ROYVA_DEFAULT_PERSON.
