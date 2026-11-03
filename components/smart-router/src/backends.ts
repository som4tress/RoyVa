// Releasing memory for a session that has been handed off.
//
// Policy, in order of importance:
//
//   1. Never unload a model. The weights must stay resident - the whole point is
//      to keep serving other sessions locally.
//   2. Only clear memory that belongs to the session being handed off.
//   3. If the engine cannot attribute cache to a session, or manages it itself,
//      do nothing and say so. A no-op is a correct outcome, not a failure.
//
// Where that lands, per engine:
//
//   llamacpp  the one engine with a real per-session primitive: a slot is one
//             sequence, and the server reports `id_slot` for each response, so
//             POST /slots/{id}?action=erase clears exactly this session's KV.
//   ollama    no cache API at all; the context is released when the request
//             finishes. No-op.
//   vllm      KV blocks are freed when the sequence ends; the prefix cache is
//             engine-managed (LRU). No-op unless evictionScope is "cache".
//   sglang    radix cache is engine-managed (LRU). No-op unless "cache".
//   tensorrt  paged KV is returned when the request ends; no cache API. No-op.

import { exec as execCallback } from "node:child_process"
import { promisify } from "node:util"
import type { BackendConfig, LocalTarget } from "./config.ts"

const exec = promisify(execCallback)

export type FetchLike = typeof fetch

export type EvictionRequest = {
  sessionID: string
  modelID: string
  target: LocalTarget
  /**
   * The llama.cpp slot that served this OpenCode session's latest request.
   * Learned from `id_slot` in the response; the only per-session attribution
   * any of these engines offers.
   */
  slot?: number
  /**
   * "session" (default) clears only what belongs to this session.
   * "cache" additionally allows global, engine-wide cache flushes.
   */
  scope?: "session" | "cache"
}

export type EvictionOutcome = {
  ok: boolean
  backend: string
  action: "cleared" | "noop"
  detail: string
}

export type EvictionDeps = {
  fetch?: FetchLike
  log?: (line: string) => void
}

const DEFAULT_TIMEOUT_MS = 3_000

class HttpError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function call(
  deps: EvictionDeps,
  url: string,
  init: RequestInit,
  timeoutMs: number,
  headers?: Record<string, string>,
): Promise<unknown> {
  const fetchImpl = deps.fetch ?? fetch
  const response = await fetchImpl(url, {
    ...init,
    headers: { ...(init.body ? { "content-type": "application/json" } : {}), ...headers, ...(init.headers ?? {}) },
    signal: AbortSignal.timeout(timeoutMs),
  })
  const text = await response.text()
  if (!response.ok) {
    throw new HttpError(`${init.method ?? "GET"} ${url} -> ${response.status} ${text.slice(0, 200)}`, response.status)
  }
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function base(backend: BackendConfig): string {
  if (!backend.baseURL) throw new Error(`backend "${backend.kind}" has no baseURL configured`)
  return backend.baseURL.replace(/\/+$/, "")
}

function noop(backend: string, detail: string): EvictionOutcome {
  return { ok: true, backend, action: "noop", detail }
}

const KEEP_MODEL_LOADED =
  "the model stays loaded; only memory attributable to this session would be cleared"

// --- ollama ---------------------------------------------------------------

function evictOllama(): EvictionOutcome {
  // Unloading with keep_alive: 0 would drop the weights too, which is exactly
  // what we must not do. Ollama exposes no cache-level API, and its context is
  // released when each request completes.
  return noop(
    "ollama",
    `no per-session cache API in Ollama - its KV context is released when the request finishes. ${KEEP_MODEL_LOADED}`,
  )
}

// --- llama.cpp (llama-server) ---------------------------------------------

type LlamaSlot = {
  id?: number
  is_processing?: boolean
  n_past?: number
  next_token?: { n_past?: number }
  prompt?: { n_tokens?: number }
}

function cachedTokens(slot: LlamaSlot): number {
  return slot.next_token?.n_past ?? slot.n_past ?? slot.prompt?.n_tokens ?? 0
}

async function evictLlamaCpp(request: EvictionRequest, deps: EvictionDeps): Promise<EvictionOutcome> {
  const backend = request.target.backend
  const timeoutMs = backend.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const root = base(backend)
  const path = backend.path ?? "/slots"

  if (request.scope !== "cache" && typeof request.slot !== "number" && backend.slots === undefined) {
    return noop("llamacpp", "no slot is attributed to this session yet, so nothing was erased")
  }

  let slots: LlamaSlot[] = []
  try {
    const response = await call(deps, `${root}${path}`, { method: "GET" }, timeoutMs, backend.headers)
    if (Array.isArray(response)) slots = response as LlamaSlot[]
  } catch (error) {
    return {
      ok: false,
      backend: "llamacpp",
      action: "noop",
      detail: `cannot read ${root}${path}: ${(error as Error).message}. Start llama-server with --slots to allow per-slot eviction.`,
    }
  }

  // Default: only this session's slot. "cache" or an explicit slot list widen it.
  const perSession = request.scope !== "cache" && backend.slots === undefined
  const wanted = perSession ? [request.slot as number] : (backend.slots ?? "all")

  const targets = slots.filter((slot) => {
    if (typeof slot.id !== "number") return false
    if (wanted !== "all" && !wanted.includes(slot.id)) return false
    if (slot.is_processing) return false
    return cachedTokens(slot) > 0
  })

  if (targets.length === 0) {
    if (perSession) {
      const busy = slots.some((slot) => slot.id === request.slot && slot.is_processing)
      return noop(
        "llamacpp",
        busy
          ? `slot ${request.slot} is still processing this session's request; nothing was erased`
          : `this session's slot ${request.slot} holds no cached tokens; nothing was erased`,
      )
    }
    return noop("llamacpp", "no idle slot held cached tokens; nothing was erased")
  }

  const erased: string[] = []
  for (const slot of targets) {
    try {
      await call(deps, `${root}/slots/${slot.id}?action=erase`, { method: "POST" }, timeoutMs, backend.headers)
      erased.push(`slot ${slot.id} (${cachedTokens(slot)} tokens)`)
    } catch (error) {
      return { ok: false, backend: "llamacpp", action: "noop", detail: `erase failed: ${(error as Error).message}` }
    }
  }
  const scope = perSession ? "this session's " : ""
  return { ok: true, backend: "llamacpp", action: "cleared", detail: `erased ${scope}${erased.join(", ")}` }
}

// --- SGLang ---------------------------------------------------------------

async function evictSglang(request: EvictionRequest, deps: EvictionDeps): Promise<EvictionOutcome> {
  if (request.scope !== "cache") {
    return noop(
      "sglang",
      `SGLang's radix cache is engine-managed (LRU) and keyed by content, not by session. Set "evictionScope": "cache" to flush it. ${KEEP_MODEL_LOADED}`,
    )
  }
  const backend = request.target.backend
  const timeoutMs = backend.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const url = `${base(backend)}${backend.path ?? "/flush_cache"}`

  try {
    await call(deps, url, { method: "POST" }, timeoutMs, backend.headers)
    return { ok: true, backend: "sglang", action: "cleared", detail: `flushed radix cache via POST ${url}` }
  } catch (error) {
    if (error instanceof HttpError && (error.status === 405 || error.status === 404)) {
      await call(deps, url, { method: "GET" }, timeoutMs, backend.headers)
      return { ok: true, backend: "sglang", action: "cleared", detail: `flushed radix cache via GET ${url}` }
    }
    throw error
  }
}

// --- vLLM -----------------------------------------------------------------

async function evictVllm(request: EvictionRequest, deps: EvictionDeps): Promise<EvictionOutcome> {
  if (request.scope !== "cache") {
    return noop(
      "vllm",
      `vLLM frees a sequence's KV blocks when the request ends and manages the prefix cache itself (LRU). Set "evictionScope": "cache" to reset that cache. ${KEEP_MODEL_LOADED}`,
    )
  }
  const backend = request.target.backend
  const timeoutMs = backend.timeoutMs ?? DEFAULT_TIMEOUT_MS
  const query = backend.resetRunningRequests ? "?reset_running_requests=true" : ""
  const paths = backend.path ? [backend.path] : ["/reset_prefix_cache", "/cache/reset", "/v1/reset_prefix_cache"]

  const tried: string[] = []
  for (const path of paths) {
    const url = `${base(backend)}${path}${query}`
    try {
      await call(deps, url, { method: "POST" }, timeoutMs, backend.headers)
      return { ok: true, backend: "vllm", action: "cleared", detail: `reset prefix cache via POST ${url}` }
    } catch (error) {
      if (error instanceof HttpError && (error.status === 404 || error.status === 405)) {
        tried.push(path)
        continue
      }
      throw error
    }
  }
  return {
    ok: false,
    backend: "vllm",
    action: "noop",
    detail:
      `no prefix-cache reset endpoint (tried ${tried.join(", ")}). Needs upstream vLLM >= 0.5 with ` +
      "--enable-prefix-caching; on this build the engine reclaims blocks itself. " +
      "Set `backend.path` for a fork, or `backend.command`.",
  }
}

// --- TensorRT-LLM ---------------------------------------------------------

function evictTensorRt(): EvictionOutcome {
  return noop(
    "tensorrt",
    `no cache API in TensorRT-LLM - paged KV is returned when the request ends. ${KEEP_MODEL_LOADED}`,
  )
}

// --- dispatch -------------------------------------------------------------

export async function evictLocalCache(request: EvictionRequest, deps: EvictionDeps = {}): Promise<EvictionOutcome> {
  const backend = request.target.backend

  // An explicit command is the user's own instruction; run it instead.
  if (backend.command) {
    try {
      const { stdout, stderr } = await exec(backend.command, {
        timeout: backend.timeoutMs ?? 30_000,
        shell: "/bin/sh",
      })
      const output = `${stdout}${stderr}`.trim()
      return {
        ok: true,
        backend: backend.kind,
        action: "cleared",
        detail: `ran eviction command${output ? `: ${output.slice(0, 300)}` : ""}`,
      }
    } catch (error) {
      return { ok: false, backend: backend.kind, action: "noop", detail: `eviction command failed: ${(error as Error).message}` }
    }
  }

  try {
    switch (backend.kind) {
      case "ollama":
        return evictOllama()
      case "llamacpp":
        return await evictLlamaCpp(request, deps)
      case "sglang":
        return await evictSglang(request, deps)
      case "vllm":
        return await evictVllm(request, deps)
      case "tensorrt":
        return evictTensorRt()
      case "none":
        return noop("none", "eviction disabled for this target")
      default:
        return { ok: false, backend: String(backend.kind), action: "noop", detail: `unsupported backend "${backend.kind}"` }
    }
  } catch (error) {
    return { ok: false, backend: backend.kind, action: "noop", detail: (error as Error).message }
  }
}
