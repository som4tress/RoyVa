// Config normalization. Everything is validated up front so a typo in
// opencode.json/router.json produces one clear error at load time instead of a
// silent no-op in the middle of a session.

export const BACKEND_KINDS = ["ollama", "llamacpp", "sglang", "vllm", "tensorrt", "none"] as const
export type BackendKind = (typeof BACKEND_KINDS)[number]

export type BackendConfig = {
  kind: BackendKind
  /** Server root, e.g. http://127.0.0.1:8000. Not used by `command`. */
  baseURL?: string
  /** Per-request timeout for eviction calls. */
  timeoutMs?: number
  headers?: Record<string, string>
  /** ollama: model to unload. Defaults to the session's local model id. */
  model?: string
  /** llamacpp: which slots to erase. Defaults to every idle slot that holds cache. */
  slots?: "all" | number[]
  /** Escape hatch: shell command run to evict (e.g. restart trtllm-serve). */
  command?: string
  /** vllm: also cancel running requests while resetting the prefix cache. */
  resetRunningRequests?: boolean
  /** Override the endpoint path (proxy in front of the server). */
  path?: string
}

export type ThroughputHint = {
  /** Billions of parameters of the local model (dense or MoE activation size). */
  paramsB: number
  /** Effective tensor throughput you actually see on this box, in TFLOPS. */
  tflops: number
  /** Hand off beyond this estimated re-prefill time, in seconds. */
  budgetSeconds: number
}

export type LocalTarget = {
  providerID: string
  /** Omit to match every model served by this provider. */
  modelID?: string
  backend: BackendConfig
  /** Per-target overrides of the global thresholds. */
  contextTokens?: number
  reasoningLoops?: number
  /** Per-target override of the prefill budget. */
  prefill?: ThroughputHint
  label?: string
}

export type RouterConfig = {
  enabled: boolean
  contextTokens: number
  reasoningLoops: number
  includeReasoningTokens: boolean
  /** Optional prefill budgeting; omit entirely to keep decisions token- and loop-based. */
  prefill?: ThroughputHint
  fallback: { providerID: string; modelID: string }
  /**
   * What to release on hand-off.
   * "session" -> only the handed-off session's cache; no-op when the engine
   *              cannot attribute it or manages it itself (default)
   * "cache"   -> also allow engine-wide cache flushes (never a model unload)
   */
  evictionScope: "session" | "cache"
  returnToLocal: "never" | "new-turn"
  returnBelowTokens: number
  announce: boolean
  dryRun: boolean
  /** Log every measurement, not just hand-offs. */
  debug: boolean
  log: boolean
  /** Optional JSONL audit trail; useful when the server's stdout is not captured. */
  logFile?: string
  local: LocalTarget[]
}

export const DEFAULT_CONFIG: RouterConfig = {
  enabled: true,
  contextTokens: 32_000,
  reasoningLoops: 25,
  includeReasoningTokens: false,
  fallback: { providerID: "openrouter", modelID: "auto" },
  evictionScope: "session",
  returnToLocal: "never",
  returnBelowTokens: 0,
  announce: true,
  dryRun: false,
  debug: false,
  log: true,
  local: [],
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function positiveInt(value: unknown, field: string, fallback: number): number {
  if (value === undefined || value === null) return fallback
  const n = typeof value === "string" ? Number(value) : value
  if (typeof n !== "number" || !Number.isFinite(n) || n <= 0) {
    throw new Error(`smart-router: \`${field}\` must be a positive number (got ${JSON.stringify(value)})`)
  }
  return Math.floor(n)
}

function bool(value: unknown, field: string, fallback: boolean): boolean {
  if (value === undefined || value === null) return fallback
  if (typeof value !== "boolean") throw new Error(`smart-router: \`${field}\` must be true or false`)
  return value
}

function stringMap(value: unknown, field: string): Record<string, string> | undefined {
  if (value === undefined || value === null) return undefined
  if (!isRecord(value)) throw new Error(`smart-router: \`${field}\` must be an object of string values`)
  const output: Record<string, string> = {}
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry !== "string") throw new Error(`smart-router: \`${field}.${key}\` must be a string`)
    output[key] = entry
  }
  return output
}

function normalizeBackend(raw: unknown, where: string): BackendConfig {
  if (!isRecord(raw)) throw new Error(`smart-router: \`${where}.backend\` must be an object`)
  const kind = raw.kind
  if (typeof kind !== "string" || !BACKEND_KINDS.includes(kind as BackendKind)) {
    throw new Error(
      `smart-router: \`${where}.backend.kind\` must be one of ${BACKEND_KINDS.join(", ")} (got ${JSON.stringify(kind)})`,
    )
  }
  const backend: BackendConfig = { kind: kind as BackendKind }

  if (raw.baseURL !== undefined && raw.baseURL !== null) {
    if (typeof raw.baseURL !== "string") throw new Error(`smart-router: \`${where}.backend.baseURL\` must be a string`)
    backend.baseURL = raw.baseURL.replace(/\/+$/, "")
  }
  if (raw.timeoutMs !== undefined) backend.timeoutMs = positiveInt(raw.timeoutMs, `${where}.backend.timeoutMs`, 5_000)
  const headers = stringMap(raw.headers, `${where}.backend.headers`)
  if (headers) backend.headers = headers
  if (typeof raw.model === "string") backend.model = raw.model
  if (typeof raw.path === "string") backend.path = raw.path
  if (typeof raw.command === "string") backend.command = raw.command
  if (raw.resetRunningRequests !== undefined) {
    backend.resetRunningRequests = bool(raw.resetRunningRequests, `${where}.backend.resetRunningRequests`, false)
  }

  if (raw.slots !== undefined) {
    if (raw.slots === "all") backend.slots = "all"
    else if (Array.isArray(raw.slots) && raw.slots.every((slot) => typeof slot === "number")) {
      backend.slots = raw.slots as number[]
    } else throw new Error(`smart-router: \`${where}.backend.slots\` must be "all" or an array of slot numbers`)
  }

  // Defaults for the built-in kinds, so a bare `{ "kind": "vllm" }` works.
  backend.baseURL ??= defaultBaseURL(backend.kind)
  return backend
}

export function defaultBaseURL(kind: BackendKind): string | undefined {
  switch (kind) {
    case "ollama":
      return "http://127.0.0.1:11434"
    case "llamacpp":
      return "http://127.0.0.1:8080"
    case "sglang":
      return "http://127.0.0.1:30000"
    case "vllm":
      return "http://127.0.0.1:8000"
    case "tensorrt":
      return "http://127.0.0.1:8001"
    default:
      return undefined
  }
}

function normalizeTarget(raw: unknown, index: number): LocalTarget {
  const where = `local[${index}]`
  if (!isRecord(raw)) throw new Error(`smart-router: \`${where}\` must be an object`)
  if (typeof raw.providerID !== "string" || raw.providerID.length === 0) {
    throw new Error(`smart-router: \`${where}.providerID\` is required`)
  }
  if (raw.modelID !== undefined && typeof raw.modelID !== "string") {
    throw new Error(`smart-router: \`${where}.modelID\` must be a string`)
  }
  const target: LocalTarget = {
    providerID: raw.providerID,
    backend: normalizeBackend(raw.backend ?? { kind: "none" }, where),
  }
  if (typeof raw.modelID === "string") target.modelID = raw.modelID
  if (typeof raw.label === "string") target.label = raw.label
  if (raw.contextTokens !== undefined) {
    target.contextTokens = positiveInt(raw.contextTokens, `${where}.contextTokens`, DEFAULT_CONFIG.contextTokens)
  }
  if (raw.reasoningLoops !== undefined) {
    target.reasoningLoops = positiveInt(raw.reasoningLoops, `${where}.reasoningLoops`, DEFAULT_CONFIG.reasoningLoops)
  }
  if (raw.prefill !== undefined) target.prefill = normalizeHint(raw.prefill, `${where}.prefill`)
  return target
}

function normalizeHint(raw: unknown, where: string): ThroughputHint {
  if (!isRecord(raw)) throw new Error(`smart-router: \`${where}\` must be an object`)
  if (raw.paramsB === undefined || raw.tflops === undefined || raw.budgetSeconds === undefined) {
    throw new Error(`smart-router: \`${where}\` requires "paramsB", "tflops" and "budgetSeconds"`)
  }
  return {
    paramsB: positiveInt(raw.paramsB, `${where}.paramsB`, 70),
    tflops: positiveInt(raw.tflops, `${where}.tflops`, 20),
    budgetSeconds: positiveInt(raw.budgetSeconds, `${where}.budgetSeconds`, 60),
  }
}

export function normalizeConfig(raw: unknown): RouterConfig {
  if (raw === undefined || raw === null) return { ...DEFAULT_CONFIG }
  if (!isRecord(raw)) throw new Error("smart-router: configuration must be a JSON object")

  const fallbackRaw = raw.fallback
  let fallback = { ...DEFAULT_CONFIG.fallback }
  if (typeof fallbackRaw === "string") {
    const [providerID, ...rest] = fallbackRaw.split("/")
    fallback = { providerID, modelID: rest.join("/") || "auto" }
  } else if (isRecord(fallbackRaw)) {
    if (typeof fallbackRaw.providerID !== "string" || !fallbackRaw.providerID) {
      throw new Error("smart-router: `fallback.providerID` is required (e.g. \"openrouter\")")
    }
    fallback = {
      providerID: fallbackRaw.providerID,
      modelID: typeof fallbackRaw.modelID === "string" && fallbackRaw.modelID ? fallbackRaw.modelID : "auto",
    }
  } else if (fallbackRaw !== undefined && fallbackRaw !== null) {
    throw new Error(`smart-router: \`fallback\` must be an object or "provider/model" (got ${JSON.stringify(fallbackRaw)})`)
  }

  const evictionScopeRaw = raw.evictionScope ?? DEFAULT_CONFIG.evictionScope
  if (evictionScopeRaw !== "session" && evictionScopeRaw !== "cache") {
    throw new Error('smart-router: `evictionScope` must be "session" or "cache"')
  }

  const returnToLocalRaw = raw.returnToLocal ?? DEFAULT_CONFIG.returnToLocal
  if (returnToLocalRaw !== "never" && returnToLocalRaw !== "new-turn") {
    throw new Error('smart-router: `returnToLocal` must be "never" or "new-turn"')
  }

  const localRaw = raw.local ?? []
  if (!Array.isArray(localRaw)) throw new Error("smart-router: `local` must be an array")

  const config: RouterConfig = {
    enabled: bool(raw.enabled, "enabled", DEFAULT_CONFIG.enabled),
    contextTokens: positiveInt(raw.contextTokens, "contextTokens", DEFAULT_CONFIG.contextTokens),
    reasoningLoops: positiveInt(raw.reasoningLoops, "reasoningLoops", DEFAULT_CONFIG.reasoningLoops),
    includeReasoningTokens: bool(raw.includeReasoningTokens, "includeReasoningTokens", false),
    fallback,
    evictionScope: evictionScopeRaw,
    returnToLocal: returnToLocalRaw,
    returnBelowTokens: positiveInt(raw.returnBelowTokens, "returnBelowTokens", 0),
    announce: bool(raw.announce, "announce", DEFAULT_CONFIG.announce),
    dryRun: bool(raw.dryRun, "dryRun", DEFAULT_CONFIG.dryRun),
    debug: bool(raw.debug, "debug", DEFAULT_CONFIG.debug),
    log: bool(raw.log, "log", DEFAULT_CONFIG.log),
    local: localRaw.map(normalizeTarget),
  }
  if (raw.prefill !== undefined) config.prefill = normalizeHint(raw.prefill, "prefill")
  if (typeof raw.logFile === "string" && raw.logFile.length > 0) config.logFile = raw.logFile
  return config
}
