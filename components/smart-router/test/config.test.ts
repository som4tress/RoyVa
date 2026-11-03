import assert from "node:assert/strict"
import { test } from "node:test"
import { normalizeConfig } from "../src/config.ts"

test("defaults are local-first with a 32k / 25-loop policy", () => {
  const config = normalizeConfig({})
  assert.equal(config.contextTokens, 32_000)
  assert.equal(config.reasoningLoops, 25)
  assert.deepEqual(config.fallback, { providerID: "openrouter", modelID: "auto" })
  assert.equal(config.local.length, 0)
  assert.equal(config.returnToLocal, "never")
})

test("backend kinds get sensible default base URLs", () => {
  const config = normalizeConfig({
    local: [{ providerID: "vllm", backend: { kind: "vllm" } }],
  })
  assert.equal(config.local[0]!.backend.baseURL, "http://127.0.0.1:8000")
})

test("unknown backend kind is rejected with the supported list", () => {
  assert.throws(
    () => normalizeConfig({ local: [{ providerID: "x", backend: { kind: "lmdeploy" } }] }),
    /must be one of ollama, llamacpp, sglang, vllm, tensorrt, none/,
  )
})

test("fallback accepts the provider/model shorthand", () => {
  const config = normalizeConfig({ fallback: "openrouter/deepseek/deepseek-chat-v3.1" })
  assert.deepEqual(config.fallback, { providerID: "openrouter", modelID: "deepseek/deepseek-chat-v3.1" })
})

test("fallback without a model resolves to auto", () => {
  const config = normalizeConfig({ fallback: { providerID: "openrouter" } })
  assert.equal(config.fallback.modelID, "auto")
})

test("per-target thresholds override the globals", () => {
  const config = normalizeConfig({
    contextTokens: 32000,
    reasoningLoops: 25,
    local: [
      { providerID: "llamacpp", backend: { kind: "llamacpp" }, contextTokens: 100000, reasoningLoops: 40 },
    ],
  })
  assert.equal(config.local[0]!.contextTokens, 100_000)
  assert.equal(config.local[0]!.reasoningLoops, 40)
})

test("invalid numeric and boolean fields fail loudly", () => {
  assert.throws(() => normalizeConfig({ contextTokens: -1 }), /positive number/)
  assert.throws(() => normalizeConfig({ enabled: "yes" }), /must be true or false/)
  assert.throws(() => normalizeConfig({ returnToLocal: "sometimes" }), /"never" or "new-turn"/)
})

test("llamacpp slot selection accepts all or an array of ids", () => {
  assert.equal(normalizeConfig({ local: [{ providerID: "l", backend: { kind: "llamacpp", slots: "all" } }] }).local[0]!.backend.slots, "all")
  assert.deepEqual(
    normalizeConfig({ local: [{ providerID: "l", backend: { kind: "llamacpp", slots: [0, 1] } }] }).local[0]!.backend.slots,
    [0, 1],
  )
  assert.throws(() => normalizeConfig({ local: [{ providerID: "l", backend: { kind: "llamacpp", slots: "some" } }] }), /"all"/)
})
