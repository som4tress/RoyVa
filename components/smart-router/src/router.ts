// Pure routing decisions. No I/O here, so the policy is unit-testable.

import type { RouterConfig, LocalTarget, ThroughputHint } from "./config.ts"
import type { ModelRef } from "./types.ts"
import type { Usage } from "./usage.ts"

export type DecisionReason = "context-tokens" | "reasoning-loops" | "prefill-budget"

export type Decision = {
  action: "promote"
  reason: DecisionReason
  /** Which limit was crossed (tokens, calls, or seconds). */
  limit: number
  /** Estimated re-prefill time of the live context, for prefill-budget decisions. */
  seconds?: number
  tokens: number
  loops: number
  measured: boolean
  target: LocalTarget
}

/** Find the local target that owns this model, if any. Exact modelID beats a provider-wide match. */
export function findLocalTarget(config: RouterConfig, model: ModelRef | undefined): LocalTarget | undefined {
  if (!model) return undefined
  const matches = config.local.filter(
    (target) => target.providerID === model.providerID && (!target.modelID || target.modelID === model.id),
  )
  return matches.find((target) => target.modelID) ?? matches[0]
}

export function thresholdsFor(config: RouterConfig, target: LocalTarget) {
  return {
    contextTokens: target.contextTokens ?? config.contextTokens,
    reasoningLoops: target.reasoningLoops ?? config.reasoningLoops,
    /** Absent unless prefill budgeting is configured (globally or per target). */
    prefill: target.prefill ?? config.prefill,
  }
}

/**
 * Seconds to prefill `tokens` from scratch on the local box.
 * Prefill work is ~2 * parameters * tokens FLOP before any attention overhead,
 * which is the floor a hand-off decision can be made against. "From scratch" is
 * the worst case the router protects: a first big turn, or a resume after the
 * engine could not keep the KV.
 */
export function estimatePrefillSeconds(tokens: number, hint: ThroughputHint): number {
  if (!hint.tflops || !hint.paramsB || tokens <= 0) return 0
  // 2 * params * tokens FLOP on a machine rated `tflops` TFLOPS.
  // paramsB = billions of parameters, tokens = whole prompt.
  return (2 * hint.paramsB * tokens) / (hint.tflops * 1e3)
}

/**
 * Decide whether a local turn should be handed off to the fallback model.
 * Both conditions are OR'd: whichever limit is crossed first wins.
 */
export function decidePromotion(input: {
  config: RouterConfig
  model: ModelRef
  usage: Usage
}): Decision | undefined {
  const { config, model, usage } = input
  if (!config.enabled) return undefined

  const target = findLocalTarget(config, model)
  if (!target) return undefined

  // Never bounce off the fallback target itself.
  if (target.providerID === config.fallback.providerID && target.modelID === config.fallback.modelID) return undefined

  const limits = thresholdsFor(config, target)

  if (usage.tokens > limits.contextTokens) {
    return {
      action: "promote",
      reason: "context-tokens",
      limit: limits.contextTokens,
      tokens: usage.tokens,
      loops: usage.loops,
      measured: usage.measured,
      target,
    }
  }

  // Prefill budget: hand off before the box pays minutes for one big prompt.
  if (limits.prefill) {
    const seconds = estimatePrefillSeconds(usage.tokens, limits.prefill)
    if (seconds > limits.prefill.budgetSeconds) {
      return {
        action: "promote",
        reason: "prefill-budget",
        limit: limits.prefill.budgetSeconds,
        seconds,
        tokens: usage.tokens,
        loops: usage.loops,
        measured: usage.measured,
        target,
      }
    }
  }

  if (usage.loops > limits.reasoningLoops) {
    return {
      action: "promote",
      reason: "reasoning-loops",
      limit: limits.reasoningLoops,
      tokens: usage.tokens,
      loops: usage.loops,
      measured: usage.measured,
      target,
    }
  }

  return undefined
}

export function fallbackRef(config: RouterConfig): ModelRef {
  return { providerID: config.fallback.providerID, id: config.fallback.modelID }
}

/**
 * When a session currently sits on the fallback model, decide whether a fresh
 * user turn should move it back to local compute.
 */
export function shouldReturnToLocal(input: {
  config: RouterConfig
  model: ModelRef | undefined
  usage: Usage
}): LocalTarget | undefined {
  const { config, model, usage } = input
  if (!config.enabled || config.returnToLocal !== "new-turn") return undefined
  if (!model) return undefined
  if (model.providerID !== config.fallback.providerID || model.id !== config.fallback.modelID) return undefined

  const target = config.local.find((entry) => entry.backend.kind !== "none")
  if (!target) return undefined

  const limits = thresholdsFor(config, target)
  const ceiling = config.returnBelowTokens > 0 ? config.returnBelowTokens : limits.contextTokens
  if (usage.tokens > ceiling) return undefined
  return target
}

export function describeDecision(decision: Decision): string {
  const seen =
    decision.reason === "context-tokens" ? decision.tokens : decision.reason === "reasoning-loops" ? decision.loops : decision.limit
  const units =
    decision.reason === "context-tokens" ? "tokens" : decision.reason === "reasoning-loops" ? "model calls this turn" : "seconds"
  const shown = decision.reason === "prefill-budget" ? decision.limit : seen
  return `${decision.reason} ${shown} > ${decision.limit} ${units}${decision.measured ? "" : " (estimated)"}`
}
