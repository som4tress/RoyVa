// Measuring "how big is this session" and "how long has this agent loop run".
//
// OpenCode records real token usage on every assistant message, so the
// preferred signal is the provider's own report on the newest turn. When a
// local server does not report usage (some llama.cpp/vLLM builds omit it), we
// fall back to a character-based estimate of the live context.

import type { SessionMessage, TokenUsage } from "./types.ts"

export type Usage = {
  /** Token footprint of the live context: what the next request would send. */
  tokens: number
  /** Model calls completed in the current user turn (the "reasoning loop" count). */
  loops: number
  /** True when `tokens` came from provider-reported usage rather than an estimate. */
  measured: boolean
}

const CHARS_PER_TOKEN = 3.6
const MESSAGE_OVERHEAD = 8

export function contextTokens(usage: TokenUsage | undefined, includeReasoning = false): number {
  if (!usage) return 0
  const cache = usage.cache ?? {}
  const total =
    (usage.input ?? 0) +
    (cache.read ?? 0) +
    (cache.write ?? 0) +
    (usage.output ?? 0) +
    (includeReasoning ? usage.reasoning ?? 0 : 0)
  return Number.isFinite(total) ? total : 0
}

export function estimateTokens(value: unknown): number {
  if (value === undefined || value === null) return 0
  let text: string
  if (typeof value === "string") text = value
  else {
    try {
      text = JSON.stringify(value) ?? ""
    } catch {
      text = String(value)
    }
  }
  return Math.ceil(text.length / CHARS_PER_TOKEN)
}

/**
 * Derive usage from the session's active context (messages after the last
 * compaction). `loops` counts assistant messages after the newest user message,
 * which is one per model call in an agent turn.
 */
export function usageFromMessages(
  messages: readonly SessionMessage[],
  options: { includeReasoning?: boolean } = {},
): Usage {
  let lastUser = -1
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index]?.type === "user") {
      lastUser = index
      break
    }
  }

  let loops = 0
  for (let index = lastUser + 1; index < messages.length; index += 1) {
    if (messages[index]?.type === "assistant") loops += 1
  }

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message?.type !== "assistant") continue
    const tokens = contextTokens(message.tokens, options.includeReasoning)
    if (tokens > 0) return { tokens, loops, measured: true }
  }

  let estimate = 0
  for (const message of messages) {
    estimate += estimateTokens(message.content) + MESSAGE_OVERHEAD
  }
  return { tokens: estimate, loops, measured: false }
}

/** Estimate usage straight from the messages a hook is about to dispatch. */
export function usageFromRequest(messages: readonly unknown[], system: readonly unknown[] = []): Usage {
  let total = 0
  for (const part of system) total += estimateTokens(part) + MESSAGE_OVERHEAD
  for (const message of messages) total += estimateTokens(message) + MESSAGE_OVERHEAD
  return { tokens: total, loops: 0, measured: false }
}
