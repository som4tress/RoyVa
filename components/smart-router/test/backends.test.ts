import assert from "node:assert/strict"
import { test } from "node:test"
import { evictLocalCache } from "../src/backends.ts"
import { normalizeConfig, type LocalTarget } from "../src/config.ts"

type Call = { url: string; method: string; body?: string }

function fakeFetch(routes: (url: string, init: RequestInit) => Response | undefined) {
  const calls: Call[] = []
  const impl = (async (input: string | URL | Request, init: RequestInit = {}) => {
    const url = String(input)
    calls.push({ url, method: init.method ?? "GET", body: init.body as string | undefined })
    return routes(url, init) ?? new Response("not found", { status: 404 })
  }) as unknown as typeof fetch
  return { impl, calls }
}

function target(providerID: string, backend: Record<string, unknown>): LocalTarget {
  return normalizeConfig({ local: [{ providerID, backend }] }).local[0]!
}

const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } })

test("ollama is a no-op: the model must stay loaded", async () => {
  const { impl, calls } = fakeFetch(() => json({}))
  const outcome = await evictLocalCache(
    { sessionID: "s", modelID: "deepseek-r1:70b", target: target("ollama", { kind: "ollama", baseURL: "http://h:11434" }) },
    { fetch: impl },
  )
  assert.equal(outcome.action, "noop")
  assert.equal(outcome.ok, true)
  assert.equal(calls.length, 0, "no unload request may be made")
  assert.match(outcome.detail, /no per-session cache API in Ollama/)
  assert.match(outcome.detail, /model stays loaded/)
})

test("llama.cpp erases only the slot that served this session", async () => {
  const { impl, calls } = fakeFetch((url) => {
    if (url.endsWith("/slots")) {
      return json([
        { id: 0, next_token: { n_past: 5_000 } },
        { id: 1, next_token: { n_past: 900 } },
      ])
    }
    return json({ ok: true })
  })

  const outcome = await evictLocalCache(
    { sessionID: "ses_a", modelID: "m", slot: 1, target: target("llamacpp", { kind: "llamacpp", baseURL: "http://h:8080" }) },
    { fetch: impl },
  )

  assert.deepEqual(
    calls.filter((call) => call.url.includes("erase")).map((call) => call.url),
    ["http://h:8080/slots/1?action=erase"],
    "slot 0 belongs to another session and must be left alone",
  )
  assert.equal(outcome.action, "cleared")
  assert.match(outcome.detail, /this session's slot 1/)
})

test("llama.cpp does nothing when no slot is attributed to the session", async () => {
  const { impl, calls } = fakeFetch(() => json([{ id: 0, next_token: { n_past: 900 } }]))
  const outcome = await evictLocalCache(
    { sessionID: "ses_a", modelID: "m", target: target("llamacpp", { kind: "llamacpp", baseURL: "http://h:8080" }) },
    { fetch: impl },
  )
  assert.equal(outcome.action, "noop")
  assert.equal(calls.length, 0, "no guessing at the server's expense")
  assert.match(outcome.detail, /no slot is attributed to this session yet/)
})

test("llama.cpp leaves a slot alone while it is still processing", async () => {
  const { impl, calls } = fakeFetch(() => json([{ id: 4, is_processing: true, next_token: { n_past: 900 } }]))
  const outcome = await evictLocalCache(
    { sessionID: "ses_a", modelID: "m", slot: 4, target: target("llamacpp", { kind: "llamacpp", baseURL: "http://h:8080" }) },
    { fetch: impl },
  )
  assert.equal(outcome.action, "noop")
  assert.equal(calls.filter((call) => call.url.includes("erase")).length, 0)
  assert.match(outcome.detail, /still processing/)
})

test("llama.cpp reports an empty session slot without erasing", async () => {
  const { impl, calls } = fakeFetch(() => json([{ id: 3, next_token: { n_past: 0 } }]))
  const outcome = await evictLocalCache(
    { sessionID: "ses_a", modelID: "m", slot: 3, target: target("llamacpp", { kind: "llamacpp", baseURL: "http://h:8080" }) },
    { fetch: impl },
  )
  assert.equal(outcome.action, "noop")
  assert.equal(calls.filter((call) => call.url.includes("erase")).length, 0)
  assert.match(outcome.detail, /slot 3 holds no cached tokens/)
})

test("llama.cpp widens to every idle slot only in cache scope", async () => {
  const { impl, calls } = fakeFetch((url) => {
    if (url.endsWith("/slots")) {
      return json([
        { id: 0, next_token: { n_past: 5_000 } },
        { id: 1, next_token: { n_past: 900 } },
        { id: 2, is_processing: true, next_token: { n_past: 1 } },
      ])
    }
    return json({})
  })
  const outcome = await evictLocalCache(
    {
      sessionID: "ses_a",
      modelID: "m",
      scope: "cache",
      target: target("llamacpp", { kind: "llamacpp", baseURL: "http://h:8080" }),
    },
    { fetch: impl },
  )
  assert.deepEqual(
    calls.filter((call) => call.url.includes("erase")).map((call) => call.url),
    ["http://h:8080/slots/0?action=erase", "http://h:8080/slots/1?action=erase"],
  )
  assert.equal(outcome.action, "cleared")
})

test("llama.cpp explains that --slots is needed when the endpoint is missing", async () => {
  const { impl } = fakeFetch(() => undefined)
  const outcome = await evictLocalCache(
    { sessionID: "s", modelID: "m", slot: 0, target: target("llamacpp", { kind: "llamacpp", baseURL: "http://h:8080" }) },
    { fetch: impl },
  )
  assert.equal(outcome.ok, false)
  assert.match(outcome.detail, /--slots/)
})

test("vllm is a no-op in session scope and resets the cache in cache scope", async () => {
  const noop = fakeFetch(() => json({ ok: true }))
  const first = await evictLocalCache(
    { sessionID: "s", modelID: "m", target: target("vllm", { kind: "vllm", baseURL: "http://h:8000" }) },
    { fetch: noop.impl },
  )
  assert.equal(first.action, "noop")
  assert.equal(noop.calls.length, 0)
  assert.match(first.detail, /engine|prefix cache itself/)
  assert.match(first.detail, /"cache"/)

  const cached = fakeFetch(() => json({ success: true }))
  const second = await evictLocalCache(
    { sessionID: "s", modelID: "m", scope: "cache", target: target("vllm", { kind: "vllm", baseURL: "http://h:8000" }) },
    { fetch: cached.impl },
  )
  assert.equal(second.action, "cleared")
  assert.equal(cached.calls[0]!.url, "http://h:8000/reset_prefix_cache")
})

test("vllm reports forks without a cache endpoint after trying the known paths", async () => {
  const { impl, calls } = fakeFetch(() => undefined)
  const outcome = await evictLocalCache(
    { sessionID: "s", modelID: "m", scope: "cache", target: target("vllm", { kind: "vllm", baseURL: "http://h:8000" }) },
    { fetch: impl },
  )
  assert.equal(outcome.ok, false)
  assert.deepEqual(
    calls.map((call) => `${call.method} ${call.url}`),
    [
      "POST http://h:8000/reset_prefix_cache",
      "POST http://h:8000/cache/reset",
      "POST http://h:8000/v1/reset_prefix_cache",
    ],
  )
  assert.match(outcome.detail, /no prefix-cache reset endpoint/)
})

test("vllm accepts a fork-specific path", async () => {
  const { impl, calls } = fakeFetch(() => json({ ok: true }))
  const outcome = await evictLocalCache(
    {
      sessionID: "s",
      modelID: "m",
      scope: "cache",
      target: target("vllm", { kind: "vllm", baseURL: "http://h:8000", path: "/admin/flush" }),
    },
    { fetch: impl },
  )
  assert.equal(outcome.action, "cleared")
  assert.deepEqual(calls.map((call) => call.url), ["http://h:8000/admin/flush"])
})

test("vllm can cancel running requests while resetting", async () => {
  const { impl, calls } = fakeFetch(() => json({ success: true }))
  const outcome = await evictLocalCache(
    {
      sessionID: "s",
      modelID: "m",
      scope: "cache",
      target: target("vllm", { kind: "vllm", baseURL: "http://h:8000", resetRunningRequests: true }),
    },
    { fetch: impl },
  )
  assert.equal(outcome.action, "cleared")
  assert.equal(calls[0]!.url, "http://h:8000/reset_prefix_cache?reset_running_requests=true")
})

test("sglang is a no-op in session scope and flushes in cache scope", async () => {
  const quiet = fakeFetch(() => json({ status: "ok" }))
  const first = await evictLocalCache(
    { sessionID: "s", modelID: "m", target: target("sglang", { kind: "sglang", baseURL: "http://h:30000" }) },
    { fetch: quiet.impl },
  )
  assert.equal(first.action, "noop")
  assert.equal(quiet.calls.length, 0)

  const { impl, calls } = fakeFetch((_url, init) =>
    (init.method ?? "GET") === "POST" ? new Response("method not allowed", { status: 405 }) : json({ status: "ok" }),
  )
  const second = await evictLocalCache(
    { sessionID: "s", modelID: "m", scope: "cache", target: target("sglang", { kind: "sglang", baseURL: "http://h:30000" }) },
    { fetch: impl },
  )
  assert.equal(second.action, "cleared")
  assert.deepEqual(calls.map((call) => call.method), ["POST", "GET"])
  assert.equal(calls[0]!.url, "http://h:30000/flush_cache")
})

test("tensorrt-llm is reported as a no-op instead of faking an endpoint", async () => {
  const { impl, calls } = fakeFetch(() => json({ status: "ok" }))
  const outcome = await evictLocalCache(
    { sessionID: "s", modelID: "m", target: target("tensorrt", { kind: "tensorrt", baseURL: "http://h:8001" }) },
    { fetch: impl },
  )
  assert.equal(outcome.action, "noop")
  assert.equal(calls.length, 0)
  assert.match(outcome.detail, /no cache API in TensorRT-LLM/)
})

test("a backend command is used as the escape hatch", async () => {
  const outcome = await evictLocalCache(
    { sessionID: "s", modelID: "m", target: target("tensorrt", { kind: "tensorrt", command: "echo restarted-trtllm" }) },
    { fetch: fakeFetch(() => undefined).impl },
  )
  assert.equal(outcome.action, "cleared")
  assert.match(outcome.detail, /restarted-trtllm/)
})

test("network failures are returned, never thrown", async () => {
  const impl = (async () => {
    throw new Error("ECONNREFUSED")
  }) as unknown as typeof fetch
  const outcome = await evictLocalCache(
    { sessionID: "s", modelID: "m", slot: 0, target: target("llamacpp", { kind: "llamacpp", baseURL: "http://h:8080" }) },
    { fetch: impl },
  )
  assert.equal(outcome.ok, false)
  assert.match(outcome.detail, /ECONNREFUSED/)
})
