// opencode-smart-router
//
// Keeps short/simple sessions on local compute and hands long ones off to the
// configured remote (OpenRouter by default) model - then frees the local KV
// allocation so the VRAM goes back into the pool.
//
//   * context tokens  > `contextTokens`  -> hand off
//   * model calls in the current turn > `reasoningLoops` -> hand off
//
// The hand-off runs inside the `context` hook, which fires immediately before a
// model dispatch. `event.model` is read-only, so the call that trips the limit
// still completes locally; the *next* turn in the agent loop uses the fallback
// model. Eviction runs in the background so the in-flight request is not
// delayed.

import { appendFileSync, readFileSync, statSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { evictLocalCache, type EvictionOutcome } from "./src/backends.ts"
import { normalizeConfig, type LocalTarget, type RouterConfig } from "./src/config.ts"
import { describeDecision, decidePromotion, estimatePrefillSeconds, fallbackRef, findLocalTarget, shouldReturnToLocal } from "./src/router.ts"
import { usageFromMessages, usageFromRequest, type Usage } from "./src/usage.ts"
import type { ModelInfo, ModelRef, PluginContext, Registration } from "./src/types.ts"

type SessionState = {
  /** Model calls observed in the current user turn. */
  loops: number
  last?: Usage
  /** The local model this session used before it was promoted. */
  localModel?: ModelRef
  /** llama.cpp slot that served this session's latest request, when known. */
  slot?: number
  promoted?: { reason: string; at: number; tokens: number; loops: number }
  eviction?: EvictionOutcome
  evictions: number
}

export default {
  id: "opencode-smart-router",
  async setup(ctx: PluginContext) {
    const options = (ctx.options ?? {}) as Record<string, unknown>
    const configSource = makeConfigSource(options)
    let config = configSource.initial
    const log = (...parts: unknown[]) => {
      if (!config.log) return
      const line = parts.map((part) => (typeof part === "string" ? part : JSON.stringify(part))).join(" ")
      console.log("[smart-router]", line)
      if (!config.logFile) return
      try {
        appendFileSync(config.logFile, `${JSON.stringify({ at: new Date().toISOString(), line })}\n`)
      } catch {
        // Losing the audit trail must never break routing.
      }
    }

    if (!config.enabled) {
      log("disabled via config; no hooks registered")
      return
    }
    if (config.debug) log("debug logging enabled")
    if (config.local.length === 0) {
      log("no `local` targets configured - the router will never hand off. See router.json")
    }

    // State is keyed by OpenCode session id: the unit the user thinks in and the
    // only unit whose model, transcript and cache attribution this plugin owns.
    const sessions = new Map<string, SessionState>()
    const MAX_TRACKED_SESSIONS = 512
    const stateFor = (sessionID: string): SessionState => {
      let state = sessions.get(sessionID)
      if (!state) {
        state = { loops: 0, evictions: 0 }
        sessions.set(sessionID, state)
        if (sessions.size > MAX_TRACKED_SESSIONS) {
          const oldest = sessions.keys().next().value
          if (oldest !== undefined) sessions.delete(oldest)
        }
      }
      return state
    }

    // `{ "modelID": "auto" }` picks an OpenRouter DeepSeek, else the first
    // enabled model the provider offers.
    let resolvedFallback: ModelRef | undefined = config.fallback.modelID === "auto" ? undefined : fallbackRef(config)
    const resolveFallback = async (): Promise<ModelRef | undefined> => {
      if (resolvedFallback) return resolvedFallback
      let models: readonly ModelInfo[] = []
      try {
        // model.list() takes a location query, not a provider id, so filter here.
        models = await ctx.model.list()
      } catch (error) {
        log("cannot list models for fallback provider:", (error as Error).message)
        return undefined
      }
      const enabled = models.filter(
        (model) => model.providerID === config.fallback.providerID && model.enabled !== false,
      )
      const preferred =
        enabled.find((model) => /deepseek/i.test(model.id)) ??
        enabled.find((model) => /deepseek/i.test(model.name ?? "")) ??
        enabled[0]
      if (!preferred) {
        log(`fallback.providerID "${config.fallback.providerID}" exposes no models; hand-off disabled`)
        return undefined
      }
      resolvedFallback = { providerID: config.fallback.providerID, id: preferred.id }
      log(`fallback model resolved to ${resolvedFallback.providerID}/${resolvedFallback.id}`)
      return resolvedFallback
    }

    // Tuning thresholds should not require touching OpenCode: re-read the
    // config file when it changes on disk.
    const refreshConfig = () => {
      const next = configSource.refresh((line) => log(line))
      if (!next) return
      const previous = config
      config = next
      if (previous.fallback.providerID !== next.fallback.providerID || previous.fallback.modelID !== next.fallback.modelID) {
        resolvedFallback = next.fallback.modelID === "auto" ? undefined : fallbackRef(next)
      }
      log(
        `config reloaded from ${configSource.source}: thresholds ${config.contextTokens} tokens / ` +
          `${config.reasoningLoops} loops${config.prefill ? ` / ${config.prefill.budgetSeconds}s prefill budget` : ""}, ` +
          `${config.local.length} local target(s)`,
      )
    }

    const announce = async (sessionID: string, text: string) => {
      if (!config.announce) return
      try {
        await ctx.session.synthetic?.({ sessionID, text })
      } catch (error) {
        log("could not post hand-off notice:", (error as Error).message)
      }
    }

    const evict = async (sessionID: string, modelID: string, target: LocalTarget, slot?: number) => {
      const started = Date.now()
      const outcome = await evictLocalCache(
        { sessionID, modelID, target, slot, scope: config.evictionScope },
        { log: (...p) => log(...p) },
      )
      const state = stateFor(sessionID)
      state.eviction = outcome
      state.evictions += 1
      log(
        `cache release [${outcome.backend}] ${outcome.action}${outcome.ok ? "" : " (failed)"} ` +
          `in ${Date.now() - started}ms: ${outcome.detail}`,
      )
      return outcome
    }

    const measure = async (sessionID: string, event: any): Promise<Usage> => {
      const state = stateFor(sessionID)
      try {
        const messages = await ctx.session.context({ sessionID })
        const usage = usageFromMessages(messages, { includeReasoning: config.includeReasoningTokens })
        // The turn counter covers the case where usage came back as an estimate.
        return { ...usage, loops: Math.max(usage.loops, state.loops) }
      } catch (error) {
        log("session.context failed, estimating from request:", (error as Error).message)
        const usage = usageFromRequest(event.messages ?? [], event.system ?? [])
        return { ...usage, loops: state.loops }
      }
    }

    const handoff = async (sessionID: string, model: ModelRef, decision: ReturnType<typeof decidePromotion>) => {
      if (!decision) return
      const state = stateFor(sessionID)
      const target = await resolveFallback()
      if (!target) return

      const summary = describeDecision(decision)
      if (config.dryRun) {
        log(`[dry-run] would hand off ${model.providerID}/${model.id} (${summary}) and evict ${decision.target.providerID}`)
        return
      }

      try {
        await ctx.session.switchModel({ sessionID, model: target })
      } catch (error) {
        log(`hand-off failed for ${sessionID}:`, (error as Error).message)
        return
      }

      state.localModel = { providerID: model.providerID, id: model.id }
      state.promoted = { reason: decision.reason, at: Date.now(), tokens: decision.tokens, loops: decision.loops }
      log(`${sessionID}: ${model.providerID}/${model.id} -> ${target.providerID}/${target.id} (${summary})`)

      // Release this session's cache, then report what actually happened. The
      // model is never unloaded, and a no-op is stated as a no-op.
      const outcome = await evict(sessionID, model.id, decision.target, state.slot)
      void announce(
        sessionID,
        `Smart router: handed off to ${target.providerID}/${target.id} (${summary}). ` +
          (outcome.action === "cleared"
            ? `Local cache cleared: ${outcome.detail}.`
            : `Nothing to clear locally: ${outcome.detail}.`),
      )
    }

    // --- per-session cache attribution ------------------------------------

    // llama.cpp reports `id_slot` in the response it sends back for a request.
    // Remembering it is what makes per-session cache release possible at all:
    // without an attributed slot the router does nothing rather than guess.
    const slotRegistrations: Registration[] = []
    const llamaProviders = new Set(
      config.evictionScope === "session"
        ? config.local.filter((entry) => entry.backend.kind === "llamacpp").map((entry) => entry.providerID)
        : [],
    )
    for (const providerID of llamaProviders) {
      slotRegistrations.push(
        await ctx.session.hook(
          "http.response",
          (event: any) => {
            if (event.kind && event.kind !== "primary") return
            const response = event.response as Response | undefined
            if (!response || typeof response.clone !== "function") return
            const sessionID = event.sessionID as string
            // Parse a copy of the body off the critical path.
            void response
              .clone()
              .text()
              .then((text) => {
                const matches = [...text.matchAll(/"id_slot"\s*:\s*(\d+)/g)]
                const match = matches[matches.length - 1]
                if (!match) return
                const slot = Number(match[1])
                if (!Number.isFinite(slot)) return
                const state = stateFor(sessionID)
                if (state.slot !== slot && config.debug) log(`session ${sessionID} is served by slot ${slot}`)
                state.slot = slot
              })
              .catch(() => {})
          },
          { providerID },
        ),
      )
    }

    // --- hooks -----------------------------------------------------------

    // New user turn: reset the loop counter and, if configured, move a
    // promoted session back onto local compute.
    const promptHook = await ctx.session.hook("prompt", async (event) => {
      refreshConfig()
      const sessionID = event.sessionID
      const state = stateFor(sessionID)
      state.loops = 0
      state.promoted = undefined

      if (config.returnToLocal !== "new-turn") return
      try {
        const session = await ctx.session.get({ sessionID })
        const messages = await ctx.session.context({ sessionID })
        const usage = usageFromMessages(messages, { includeReasoning: config.includeReasoningTokens })
        const target = shouldReturnToLocal({ config, model: session.model, usage })
        if (!target) return
        const restore = state.localModel ?? (target.modelID ? { providerID: target.providerID, id: target.modelID } : undefined)
        if (!restore) return
        await ctx.session.switchModel({ sessionID, model: restore })
        log(`${sessionID}: back to local ${restore.providerID}/${restore.id} (${usage.tokens} tokens)`)
      } catch (error) {
        log("return-to-local failed:", (error as Error).message)
      }
    })

    const contextHook = await ctx.session.hook("context", async (event) => {
      // The context hook carries no `kind` (only the HTTP/WS hooks do); when a
      // kind is present, only the agent loop should be routed.
      if (event.kind && event.kind !== "primary") return
      refreshConfig()
      const sessionID = event.sessionID as string
      const model = event.model as ModelRef
      const state = stateFor(sessionID)

      // Only local models are worth measuring.
      if (!findLocalTarget(config, model)) return

      state.loops += 1
      const usage = await measure(sessionID, event)
      state.last = usage
      if (config.debug) {
        log(
          `measure ${sessionID}: ${model.providerID}/${model.id} ${usage.tokens} tokens ` +
            `(${usage.measured ? "reported" : "estimated"}), ${usage.loops} loop(s)`,
        )
      }

      const decision = decidePromotion({ config, model, usage })
      if (!decision) return
      await handoff(sessionID, model, decision)    })

    // --- commands --------------------------------------------------------

    const commandRegistration = await ctx.command?.transform((editor) => {
      editor.add({
        name: "router-status",
        description: "Show smart router state for this session",
        execute: async ({ sessionID }: { sessionID: string }) => {
          const session = await ctx.session.get({ sessionID }).catch(() => undefined)
          const state = stateFor(sessionID)
          const model = session?.model
          const target = findLocalTarget(config, model)
          const limits = target
            ? {
                contextTokens: target.contextTokens ?? config.contextTokens,
                reasoningLoops: target.reasoningLoops ?? config.reasoningLoops,
                prefill: target.prefill ?? config.prefill,
              }
            : { contextTokens: config.contextTokens, reasoningLoops: config.reasoningLoops, prefill: config.prefill }
          const prefillLine = limits.prefill
            ? `\nprefill: ~${estimatePrefillSeconds(state.last?.tokens ?? 0, limits.prefill).toFixed(0)}s ` +
              `(budget ${limits.prefill.budgetSeconds}s, ${limits.prefill.paramsB}B @ ${limits.prefill.tflops} TFLOPS)`
            : "\nprefill: not budgeted"
          const lines = [
            `model: ${model ? `${model.providerID}/${model.id}` : "unknown"}`,
            `route: ${target ? `local (${target.backend.kind})` : `remote/other (${config.fallback.providerID}/${config.fallback.modelID})`}`,
            `context: ${state.last?.tokens ?? 0} / ${limits.contextTokens} tokens${state.last && !state.last.measured ? " (estimated)" : ""}`,
            `loops this turn: ${state.loops} / ${limits.reasoningLoops}`,
            prefillLine,
            state.promoted
              ? `promoted: ${state.promoted.reason} at ${new Date(state.promoted.at).toISOString()}`
              : "promoted: no",
            state.eviction
              ? `last cache release: ${state.eviction.backend} ${state.eviction.action}` +
                `${state.eviction.ok ? "" : " (failed)"} - ${state.eviction.detail}`
              : "last cache release: none",
            `releases run: ${state.evictions}`,
          ]
          await ctx.session.synthetic?.({ sessionID, text: `Smart router\n${lines.join("\n")}` })
        },
      })

      editor.add({
        name: "router-evict",
        description: "Run a cache release now on this session's local backend",
        execute: async ({ sessionID }: { sessionID: string }) => {
          const session = await ctx.session.get({ sessionID }).catch(() => undefined)
          const state = stateFor(sessionID)
          const model = session?.model
          const target = findLocalTarget(config, model) ?? config.local[0]
          if (!target) {
            await ctx.session.synthetic?.({
              sessionID,
              text: "Smart router: no local target configured, nothing to evict.",
            })
            return
          }
          const outcome = await evict(sessionID, state.localModel?.id ?? model?.id ?? "unknown", target, state.slot)
          await ctx.session.synthetic?.({
            sessionID,
            text: `Smart router cache release [${outcome.backend}] ${outcome.action === "cleared" ? "cleared" : "no-op"}: ${outcome.detail}`,
          })
        },
      })
    })

    log(
      `ready: ${config.local.length} local target(s), thresholds ${config.contextTokens} tokens / ` +
        `${config.reasoningLoops} loops, fallback ${config.fallback.providerID}/${config.fallback.modelID}`,
    )

    return () => {
      void promptHook?.dispose()
      void contextHook?.dispose()
      void commandRegistration?.dispose()
      for (const registration of slotRegistrations) void registration.dispose()
      sessions.clear()
    }
  },
}

type ConfigSource = {
  initial: RouterConfig
  source: string
  /** Returns a new config when the file changed on disk, otherwise undefined. */
  refresh(log: (line: string) => void): RouterConfig | undefined
}

function makeConfigSource(options: Record<string, unknown>): ConfigSource {
  // Inline config in opencode.json wins, then an explicit path, then env, then
  // the router.json that ships next to this file.
  if (options.config && typeof options.config === "object") {
    return { initial: normalizeConfig(options.config), source: "opencode.json options", refresh: () => undefined }
  }

  const explicitPath =
    typeof options.configPath === "string"
      ? options.configPath
      : typeof options.config === "string"
        ? options.config
        : process.env.SMART_ROUTER_CONFIG
  const path = explicitPath ?? fileURLToPath(new URL("./router.json", import.meta.url))

  let initial: RouterConfig
  let stamp = fileStamp(path)
  try {
    initial = normalizeConfig(readJson(path))
  } catch (error) {
    if ((error as { code?: string }).code === "ENOENT" && !explicitPath) {
      initial = normalizeConfig({})
    } else {
      throw error
    }
  }

  return {
    initial,
    source: path,
    refresh(log) {
      const next = fileStamp(path)
      if (next === stamp) return undefined
      stamp = next
      try {
        return normalizeConfig(readJson(path))
      } catch (error) {
        // keep previous settings on a bad edit
        log(`config reload failed, keeping previous settings: ${(error as Error).message}`)
        return undefined
      }
    },
  }
}

function fileStamp(path: string): string {
  try {
    const info = statSync(path)
    return `${info.mtimeMs}:${info.size}`
  } catch {
    return "missing"
  }
}

function readJson(path: string): unknown {
  const text = readFileSync(path, "utf8")
  try {
    return JSON.parse(text)
  } catch (error) {
    throw new Error(`smart-router: ${path} is not valid JSON - ${(error as Error).message}`)
  }
}
