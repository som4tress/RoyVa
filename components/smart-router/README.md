# opencode-smart-router

Keeps short, simple sessions on your local box and hands long ones to OpenRouter
— then releases the cache that session was holding, without touching the model.

Triggers, whichever trips first:

| trigger | config | default |
|---|---|---|
| context grows past N tokens | `contextTokens` | `32000` |
| the agent loop runs more than N model calls in one user turn | `reasoningLoops` | `25` |
| the live context would take an estimated N seconds to re-prefill | `prefill` | off |

When a trigger fires the router:

1. switches **that OpenCode session's** model to your configured fallback (`openrouter/<model>`),
2. releases the cache that session was holding, if the engine can attribute it,
3. posts a one-line note in the transcript saying which of the two happened,
4. leaves the session remote for the rest of the conversation.

State is keyed by OpenCode session id (`ses_…`), so only that session's model
moves; other sessions keep running locally untouched.

## Releasing memory: three rules

1. **Never unload the model.** The weights stay resident — the box keeps serving
   every other session. There is no `keep_alive: 0` anywhere in this plugin.
2. **Only touch what belongs to the handed-off session.**
3. **If the engine can't attribute cache to a session, or already manages it,
   do nothing and say so.** A no-op is a correct outcome, not a failure.

That lands differently per engine, because they age their caches differently:

| backend | what the hand-off does | why |
|---|---|---|
| `llamacpp` | erases the slot that served this session (`POST /slots/{id}?action=erase`) | a slot is one sequence, and the server reports `id_slot` per response — the only real per-session handle in this list |
| `ollama` | **no-op** | no cache API at all; the context is freed when the request finishes, the model stays loaded |
| `vllm` | **no-op** by default | KV blocks are freed when the sequence ends; the prefix cache is engine-managed (LRU) |
| `sglang` | **no-op** by default | radix cache is engine-managed (LRU) |
| `tensorrt` | **no-op** | paged KV returns to the pool when the request ends |

The no-ops are deliberate: those engines already do this themselves, and the only
way to force their global caches empty is to flush them for *every* session,
which contradicts rule 2. If you do want that, `evictionScope: "cache"` opts in
to the engine-wide flush (vLLM `/reset_prefix_cache`, SGLang `/flush_cache`,
llama.cpp all idle slots). It still never unloads a model.

Nothing is erased while a request is in flight — a busy slot is skipped, and
vLLM resets leave running requests alone unless you set
`resetRunningRequests`.

Two boundaries worth knowing:

- **The transcript is not the cache.** Messages live in OpenCode's database and
  do *not* shrink on hand-off — they are re-sent to OpenRouter. Only the server's
  cache is releasable, which is why the hand-off is about the box, not the tokens.
- **Cache is keyed by content, not by session.** That is exactly why llama.cpp
  is the only engine where "this session's cache" is a thing you can name.

This is a standalone plugin directory. **Nothing in your OpenCode installation is
modified** — you opt in by applying one patch (below) or adding one config entry.

## Install

Apply the patch against your config directory:

```sh
cd ~/.config/opencode
patch -p1 --dry-run < opencode-smart-router/patches/opencode.json.patch   # preview
patch -p1          < opencode-smart-router/patches/opencode.json.patch   # apply
```

The patch only appends a `plugins` entry; `model`, `mcp`, and `instructions` are
preserved. OpenCode reloads plugins on config change — no restart needed.

Or add the entry by hand:

```jsonc
{
  "plugins": [
    { "package": "~/opencode-smart-router" }
  ]
}
```

Uninstall: delete that `plugins` entry (or `patch -R -p1 < …/opencode.json.patch`).

Verify it loaded:

```sh
opencode api get /api/plugin | grep -o 'opencode-smart-router'
```

## Configure

The plugin reads `router.json` next to `index.ts` and **re-reads it on every model
call when the file changes**, so threshold tuning needs no reload. Override the
path with `SMART_ROUTER_CONFIG=/path/to/router.json`, or pass options inline:

```jsonc
{
  "plugins": [
    { "package": "…/opencode-smart-router", "options": { "configPath": "/etc/smart-router.json" } }
  ]
}
```

### Top-level keys

| key | default | meaning |
|---|---|---|
| `enabled` | `true` | master switch |
| `contextTokens` | `32000` | hand off when the live context exceeds this |
| `reasoningLoops` | `25` | hand off after this many model calls in one user turn |
| `prefill` | off | `{paramsB, tflops, budgetSeconds}` — hand off when re-prefilling the live context would exceed `budgetSeconds` (see below) |
| `includeReasoningTokens` | `false` | count reasoning tokens toward the context size |
| `fallback` | `openrouter` / `auto` | `{providerID, modelID}` or `"provider/model"`; `auto` picks the first OpenRouter DeepSeek |
| `evictionScope` | `"session"` | `"session"` only touches the handed-off session's cache (no-op where the engine can't attribute it); `"cache"` also allows engine-wide cache flushes |
| `returnToLocal` | `"never"` | `"new-turn"` moves a promoted session back to local on the next prompt |
| `returnBelowTokens` | `0` | with `new-turn`: only return if context is under this; `0` means the local threshold |
| `announce` | `true` | post a synthetic note on hand-off |
| `dryRun` | `false` | log decisions, never switch or evict |
| `debug` | `false` | log every measurement |
| `log` | `true` | log to the server log |
| `logFile` | unset | also append JSONL to this path (useful when server stdout is not captured) |
| `local` | `[]` | the local targets (below) |

### `local` entries

```jsonc
{
  "providerID": "ollama",        // must match the OpenCode provider ID
  "modelID": "deepseek-r1:70b",  // optional: omit to match every model of that provider
  "contextTokens": 48000,        // optional per-target override
  "reasoningLoops": 40,          // optional per-target override
  "prefill": { "paramsB": 70, "tflops": 20, "budgetSeconds": 600 },  // optional per-target override
  "backend": { "kind": "ollama" }
}
```

An entry with an exact `modelID` wins over a provider-wide entry.

### Prefill budget trigger

Token counts measure *how big* the session is, not *how expensive it is to the
box*. A 30k-token context is trivial for an 8B model and painful for a 70B —
but the cost that actually hurts is the **re-prefill**: when a session's KV is
not resident (first big turn, or after the engine reclaimed it), the local
model must process the whole prompt from scratch before generating a token.
That cost is arithmetic, not memory, and it scales with model size.

The `prefill` trigger estimates that cost and hands off before paying it:

```
seconds ≈ 2 × paramsB × tokens / (tflops × 1000)
```

— 2 FLOP per parameter per token (prefill's arithmetic floor), a model of
`paramsB` billion parameters, a prompt of `tokens` tokens, on hardware that
delivers `tflops` TFLOPS effective. Examples with `tflops: 20`:

| context | 8B model | 70B model |
|---|---|---|
| 20k tokens | 16s | 140s |
| 60k tokens | 48s | 420s |
| 100k tokens | 80s | 700s |

```jsonc
{
  "prefill": { "paramsB": 70, "tflops": 20, "budgetSeconds": 600 },
  "local": [
    { "providerID": "vllm", "backend": { "kind": "vllm", "baseURL": "…" }, "prefill": { "paramsB": 8, "tflops": 30, "budgetSeconds": 30 } }
  ]
}
```

Notes:

- `paramsB` is the dense or active parameter count (for a 4-bit MoE, count the
  active experts' parameters, not the size on disk).
- `tflops` is what *you* measure, not the spec-sheet number. `prefill_bench`
  style tooling or the delta between a cold and warm prompt will get you close;
  on a memory-bandwidth-bound box the effective number is usually well below
  peak.
- This is a floor estimate — it ignores attention and scheduling overhead, so
  real prefill runs somewhat slower. Set `budgetSeconds` to the time you'd
  genuinely wait, and let the margin absorb the overhead.
- Omit the block entirely and the router behaves exactly as before (token +
  loop thresholds only).

## Backend reference

Exactly which call is made, and the knob that changes it:

| `kind` | call | notes |
|---|---|---|
| `ollama` | none (no-op) | use `backend.command` if you ever want a real unload |
| `llamacpp` | `GET /slots`, then `POST /slots/{id}?action=erase` for this session's slot | needs `llama-server --slots`; `backend.slots` pins an explicit set |
| `sglang` | `POST /flush_cache`, falls back to `GET` | only in `"cache"` scope |
| `vllm` | `POST /reset_prefix_cache`, then `/cache/reset`, `/v1/reset_prefix_cache` | only in `"cache"` scope; needs `--enable-prefix-caching` |
| `tensorrt` | none (no-op) | no flush endpoint exists; use `backend.command` |
| `none` | — | routing only, no eviction call |

Every backend accepts `baseURL`, `timeoutMs`, `headers`, `path` (override the
endpoint), and `command` (shell escape hatch, run instead of the built-in call —
use it for TensorRT-LLM restarts or anything unlisted).

A hand-off never *reuses* the cache remotely — OpenRouter cannot see it. What the
release buys you is the memory back, so the next local request (another session,
or this one after `returnToLocal`) starts with more room, while the model keeps
serving.

## Commands

| command | what it does |
|---|---|
| `/router-status` | model, route, tokens vs threshold, loops vs budget, last promotion, last cache release (cleared or no-op, and why) |
| `/router-evict` | run a cache release now for this session's backend (handy for testing a backend) |

## Behaviour details worth knowing

- The hand-off runs in the `context` hook, which fires immediately before a
  model dispatch. `event.model` is read-only, so **the call that trips the limit
  still completes locally**; the next turn in the loop is remote.
- Token count is the provider-reported usage of the newest assistant message
  (`input + output + cache.read + cache.write`), which is exactly the prompt
  footprint the local server processed. If a server reports no usage, it falls
  back to a character estimate and labels it `(estimated)`.
- "Reasoning loops" = assistant messages after the newest user message, i.e.
  model calls in the current turn. It resets on every new prompt.
- Session tracking is bounded (512 sessions); older entries are dropped first.
  The slot map is learned per OpenCode session and only used when the target
  backend is llama.cpp.
- Set `contextTokens` **below the local server's `max_model_len`**, otherwise the
  server rejects the request before the threshold is ever crossed.
- The cache release runs after the switch and before the transcript note, so the
  note reports what actually happened. It is time-bounded (3s by default) and a
  failure or unreachable backend only logs a warning — it never blocks the turn.
- No request is made at all when the outcome would be a no-op, so a session on
  vLLM/Ollama/SGLang/TensorRT costs the local server zero extra calls.

## Example: DGX Spark, 4-bit 70B on vLLM, OpenRouter fallback

```jsonc
{
  "contextTokens": 32000,
  "reasoningLoops": 30,
  "fallback": { "providerID": "openrouter", "modelID": "deepseek/deepseek-chat-v3.1" },
  "local": [
    { "providerID": "vllm", "modelID": "deepseek-distill-70b", "backend": { "kind": "vllm", "baseURL": "http://127.0.0.1:8000" } }
  ]
}
```

## Tests

```sh
cd ~/opencode-smart-router
node --test test/*.test.ts    # 54 tests, no dependencies, no network
```

`test/plugin.test.ts` drives the real plugin against a fake OpenCode server
context, so hook names, the hook event shape, and switch-then-evict ordering are
covered — not just the pure policy functions.

## Files

```
index.ts                 plugin entry (hooks, commands, config reload)
src/config.ts            config normalization and validation
src/router.ts            pure decisions: promote / return-to-local
src/usage.ts             token + loop measurement
src/backends.ts          cache release per engine (no-ops documented inline)
patches/opencode.json.patch
router.json              active config
test/                    unit + wiring tests
```
