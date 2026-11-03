import assert from "node:assert/strict"
import { test } from "node:test"
import { normalizeConfig } from "../src/config.ts"
import { decidePromotion, estimatePrefillSeconds, findLocalTarget, shouldReturnToLocal } from "../src/router.ts"

const config = normalizeConfig({
  contextTokens: 32_000,
  reasoningLoops: 25,
  fallback: { providerID: "openrouter", modelID: "deepseek/deepseek-chat" },
  local: [
    { providerID: "vllm", modelID: "qwen35-9b", backend: { kind: "vllm", baseURL: "http://localhost:8000" } },
    { providerID: "ollama", backend: { kind: "ollama", baseURL: "http://localhost:11434" } },
  ],
})

const local = { providerID: "vllm", id: "qwen35-9b" }

test("hands off when the estimated re-prefill would take too long", () => {
  const budgeted = {
    ...config,
    contextTokens: 1_000_000,
    reasoningLoops: 99,
    prefill: { paramsB: 70, tflops: 20, budgetSeconds: 600 },
  } as typeof config
  // 2 * 70 * 100k / (20 * 1000) = 700s > 600s
  const decision = decidePromotion({ config: budgeted, model: local, usage: { tokens: 100_000, loops: 1, measured: true } })
  assert.equal(decision?.reason, "prefill-budget")
  assert.equal(decision?.limit, 600)
  assert.ok(decision && decision.seconds! > 600 && decision.seconds! < 800, `got ${decision?.seconds}`)
})

test("prefill budget stays local when the estimate is under the budget", () => {
  const budgeted = {
    ...config,
    contextTokens: 1_000_000,
    reasoningLoops: 99,
    prefill: { paramsB: 70, tflops: 20, budgetSeconds: 600 },
  } as typeof config
  // 2 * 70 * 60k / 20000 = 420s
  assert.equal(
    decidePromotion({ config: budgeted, model: local, usage: { tokens: 60_000, loops: 1, measured: true } }),
    undefined,
  )
})

test("a per-target prefill hint overrides the global one", () => {
  const custom = normalizeConfig({
    prefill: { paramsB: 70, tflops: 20, budgetSeconds: 600 },
    local: [{ providerID: "vllm", backend: { kind: "vllm" }, prefill: { paramsB: 8, tflops: 40, budgetSeconds: 5 } }],
  })
  // Target hint: 2 * 8 * 20k / (40 * 1000) = 8s > 5s budget -> promote.
  // Global hint would have said ~700s under a 600s budget and stayed local.
  const decision = decidePromotion({ config: custom, model: local, usage: { tokens: 20_000, loops: 1, measured: true } })
  assert.equal(decision?.reason, "prefill-budget")
  assert.equal(decision?.limit, 5)
})

test("estimatePrefillSeconds matches the 2*params*tokens/TFLOPS model", () => {
  assert.equal(estimatePrefillSeconds(100_000, { paramsB: 70, tflops: 20, budgetSeconds: 600 }), 700)
  assert.equal(estimatePrefillSeconds(0, { paramsB: 70, tflops: 20, budgetSeconds: 600 }), 0)
})

test("stays local under both limits", () => {
  const decision = decidePromotion({
    config,
    model: local,
    usage: { tokens: 31_999, loops: 25, measured: true },
  })
  assert.equal(decision, undefined)
})

test("hands off when the context crosses the token limit", () => {
  const decision = decidePromotion({ config, model: local, usage: { tokens: 32_001, loops: 2, measured: true } })
  assert.equal(decision?.reason, "context-tokens")
  assert.equal(decision?.limit, 32_000)
  assert.equal(decision?.target.backend.kind, "vllm")
})

test("hands off when the agent loop runs too many steps", () => {
  const decision = decidePromotion({ config, model: local, usage: { tokens: 1_200, loops: 26, measured: true } })
  assert.equal(decision?.reason, "reasoning-loops")
  assert.equal(decision?.limit, 25)
})

test("never re-promotes a session that is already remote", () => {
  const decision = decidePromotion({
    config,
    model: { providerID: "openrouter", id: "deepseek/deepseek-chat" },
    usage: { tokens: 200_000, loops: 99, measured: true },
  })
  assert.equal(decision, undefined)
})

test("matches a provider-wide target when no modelID is given", () => {
  const target = findLocalTarget(config, { providerID: "ollama", id: "deepseek-r1:70b" })
  assert.equal(target?.backend.kind, "ollama")
})

test("an exact modelID match beats a provider-wide match", () => {
  const mixed = normalizeConfig({
    local: [
      { providerID: "vllm", backend: { kind: "vllm" } },
      { providerID: "vllm", modelID: "big-model", backend: { kind: "none" } },
    ],
  })
  assert.equal(findLocalTarget(mixed, { providerID: "vllm", id: "big-model" })?.modelID, "big-model")
  assert.equal(findLocalTarget(mixed, { providerID: "vllm", id: "small-model" })?.modelID, undefined)
})

test("per-target thresholds apply instead of the globals", () => {
  const custom = normalizeConfig({
    contextTokens: 32_000,
    local: [{ providerID: "vllm", backend: { kind: "vllm" }, contextTokens: 64_000 }],
  })
  assert.equal(decidePromotion({ config: custom, model: local, usage: { tokens: 40_000, loops: 1, measured: true } }), undefined)
  assert.equal(
    decidePromotion({ config: custom, model: local, usage: { tokens: 64_001, loops: 1, measured: true } })?.reason,
    "context-tokens",
  )
})

test("return to local only happens on a fresh turn under the ceiling", () => {
  const returning = normalizeConfig({
    ...{ contextTokens: 32_000, returnToLocal: "new-turn", returnBelowTokens: 8_000 },
    fallback: { providerID: "openrouter", modelID: "deepseek/deepseek-chat" },
    local: [{ providerID: "vllm", modelID: "qwen35-9b", backend: { kind: "vllm" } }],
  })
  const remote = { providerID: "openrouter", id: "deepseek/deepseek-chat" }
  assert.ok(shouldReturnToLocal({ config: returning, model: remote, usage: { tokens: 7_000, loops: 0, measured: true } }))
  assert.equal(shouldReturnToLocal({ config: returning, model: remote, usage: { tokens: 9_000, loops: 0, measured: true } }), undefined)
  assert.equal(shouldReturnToLocal({ config: returning, model: local, usage: { tokens: 100, loops: 0, measured: true } }), undefined)
  assert.equal(
    shouldReturnToLocal({ config, model: remote, usage: { tokens: 100, loops: 0, measured: true } }),
    undefined,
    "default returnToLocal is never",
  )
})
