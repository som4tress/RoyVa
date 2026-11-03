// Structural types for the small slice of the OpenCode V2 plugin server API
// that this router uses. Deliberately local (no `@opencode/plugin` import) so
// the plugin directory loads with zero dependencies installed.

export type ModelRef = { providerID: string; id: string; variant?: string }

export type TokenUsage = {
  input?: number
  output?: number
  reasoning?: number
  cache?: { read?: number; write?: number }
}

export type SessionMessage = {
  id?: string
  type?: string
  model?: ModelRef
  tokens?: TokenUsage
  content?: unknown
  finish?: string
  time?: { created?: number; completed?: number }
}

export type ModelInfo = {
  providerID?: string
  id: string
  name?: string
  enabled?: boolean
}

export type Registration = { dispose(): Promise<void> | void }

export type SessionHookEvent = {
  readonly sessionID: string
  readonly model: ModelRef
  readonly agent: string
  readonly kind: "primary" | "compaction" | "title" | "generate"
}

export type ContextHookEvent = SessionHookEvent & {
  system: unknown[]
  messages: unknown[]
  tools: Record<string, unknown>
  options: Record<string, unknown>
}

export type PluginContext = {
  readonly options: Record<string, unknown>
  readonly app: { readonly version?: string }
  readonly location: { readonly directory: string; readonly project?: { readonly id?: string } }
  readonly session: {
    get(input: { sessionID: string }): Promise<{ id: string; model?: ModelRef; title?: string }>
    context(input: { sessionID: string }): Promise<readonly SessionMessage[]>
    switchModel(input: { sessionID: string; model: ModelRef }): Promise<void>
    synthetic?(input: { sessionID: string; text: string }): Promise<unknown>
    hook(
      name: "prompt" | "context" | "compaction" | "generate",
      callback: (event: any) => void | Promise<void>,
      options?: { providerID?: string },
    ): Promise<Registration>
  }
  readonly model: {
    list(providerID?: string): Promise<readonly ModelInfo[]>
  }
  readonly command?: {
    transform(callback: (editor: {
      add(definition: { name: string; description?: string; execute: (input: any) => Promise<void> }): void
    }) => void): Promise<Registration>
  }
  readonly storage?: {
    get(key: string): Promise<unknown>
    set(key: string, value: unknown): Promise<void>
  }
}
