// Wiring test: drives the real plugin against a fake OpenCode server context.
// This is the layer that unit tests cannot reach - hook names, the shape of the
// hook event, and the order of switch-then-evict.

import assert from "node:assert/strict"
import { mkdtempSync, utimesSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { test } from "node:test"
import plugin from "../index.ts"
import type { ModelRef, PluginContext } from "../src/types.ts"

type Harness = {
  ctx: PluginContext
  hooks: Record<string, (event: any) => unknown>
  switched: ModelRef[]
  synthetic: string[]
  commands: string[]
  select(model: ModelRef): void
}

function harness(options: {
  config?: Record<string, unknown>
  configPath?: string
  model?: ModelRef
  messages?: unknown[]
}): Harness {
  const hooks: Record<string, (event: any) => unknown> = {}
  const switched: ModelRef[] = []
  const synthetic: string[] = []
  const commands: string[] = []
  let current = options.model ?? { providerID: "vllm", id: "qwen35-9b" }

  const ctx = {
    options: options.configPath ? { configPath: options.configPath } : { config: options.config },
    app: { version: "test" },
    location: { directory: "/tmp" },
    session: {
      get: async () => ({ id: "ses_test", model: current }),
      context: async () => options.messages ?? [],
      switchModel: async ({ model }: { model: ModelRef }) => {
        switched.push(model)
        current = model
      },
      synthetic: async ({ text }: { text: string }) => {
        synthetic.push(text)
      },
      hook: async (name: string, callback: (event: any) => unknown) => {
        hooks[name] = callback
        return { dispose() {} }
      },
    },
    model: {
      list: async () => [
        { providerID: "opencode", id: "gpt-4o-mini", enabled: true },
        { providerID: "openrouter", id: "some/other-model", enabled: true },
        { providerID: "openrouter", id: "deepseek/deepseek-chat-v3.1", enabled: true },
      ],
    },
    command: {
      transform: async (callback: (editor: any) => void) => {
        callback({
          add: (definition: { name: string }) => {
            commands.push(definition.name)
          },
        })
        return { dispose() {} }
      },
    },
  } as unknown as PluginContext

  return {
    ctx,
    hooks,
    switched,
    synthetic,
    commands,
    select: (model: ModelRef) => {
      current = model
    },
  }
}

const baseConfig = {
  log: false,
  contextTokens: 100,
  reasoningLoops: 25,
  fallback: { providerID: "openrouter", modelID: "auto" },
  local: [{ providerID: "vllm", backend: { kind: "none" } }],
}

const localModel = { providerID: "vllm", id: "qwen35-9b" }

const assistantTurn = (input: number) => [
  { type: "user", content: [{ type: "text", text: "hi" }] },
  { type: "assistant", content: [], tokens: { input, output: 4, cache: { read: 0, write: 0 } } },
]

const settle = () => new Promise((resolve) => setTimeout(resolve, 20))

test("registers the context and prompt hooks plus the router commands", async () => {
  const h = harness({ config: baseConfig })
  await plugin.setup(h.ctx)
  assert.ok(h.hooks.context, "context hook registered")
  assert.ok(h.hooks.prompt, "prompt hook registered")
  assert.deepEqual(h.commands, ["router-status", "router-evict"])
})

test("hands off to the resolved fallback when the context is too big", async () => {
  const h = harness({ config: baseConfig, messages: assistantTurn(9_000) })
  await plugin.setup(h.ctx)

  await h.hooks.context!({ sessionID: "ses_test", model: localModel, system: [], messages: [], options: {} })
  await settle()

  assert.deepEqual(h.switched, [{ providerID: "openrouter", id: "deepseek/deepseek-chat-v3.1" }])
  assert.match(h.synthetic.join("\n"), /handed off to openrouter\/deepseek\/deepseek-chat-v3\.1/)
  assert.match(h.synthetic.join("\n"), /context-tokens 9004 > 100/)
})

test("stays local while under both limits", async () => {
  const h = harness({ config: baseConfig, messages: assistantTurn(50) })
  await plugin.setup(h.ctx)

  await h.hooks.context!({ sessionID: "ses_test", model: localModel, system: [], messages: [], options: {} })
  await settle()

  assert.deepEqual(h.switched, [])
})

test("ignores hooks that carry a non-primary kind", async () => {
  const h = harness({ config: baseConfig, messages: assistantTurn(9_000) })
  await plugin.setup(h.ctx)

  await h.hooks.context!({ kind: "title", sessionID: "ses_test", model: localModel, system: [], messages: [], options: {} })
  await settle()

  assert.deepEqual(h.switched, [])
})

test("dry run reports the decision without switching", async () => {
  const h = harness({ config: { ...baseConfig, dryRun: true }, messages: assistantTurn(9_000) })
  await plugin.setup(h.ctx)

  await h.hooks.context!({ sessionID: "ses_test", model: localModel, system: [], messages: [], options: {} })
  await settle()

  assert.deepEqual(h.switched, [])
  assert.match(h.synthetic.join("\n"), /^$/)
})

test("hands off once the agent loop exceeds its step budget", async () => {
  const h = harness({
    config: { ...baseConfig, contextTokens: 1_000_000, reasoningLoops: 2 },
    messages: [
      { type: "user", content: [] },
      { type: "assistant", content: [], tokens: { input: 10, output: 1 } },
      { type: "assistant", content: [], tokens: { input: 20, output: 1 } },
      { type: "assistant", content: [], tokens: { input: 30, output: 1 } },
    ],
  })
  await plugin.setup(h.ctx)

  await h.hooks.context!({ sessionID: "ses_test", model: localModel, system: [], messages: [], options: {} })
  await settle()

  assert.deepEqual(h.switched, [{ providerID: "openrouter", id: "deepseek/deepseek-chat-v3.1" }])
  assert.match(h.synthetic.join("\n"), /reasoning-loops 3 > 2/)
})

test("a new user turn resets the loop counter", async () => {
  const h = harness({ config: { ...baseConfig, contextTokens: 1_000_000, reasoningLoops: 2 }, messages: [] })
  await plugin.setup(h.ctx)
  const event = { sessionID: "ses_test", model: localModel, system: [], messages: [], options: {} }

  await h.hooks.prompt!({ sessionID: "ses_test", prompt: { text: "go" } })
  await h.hooks.context!(event)
  await h.hooks.context!(event)
  // Third would trip the budget, so reset first and confirm it does not.
  await h.hooks.prompt!({ sessionID: "ses_test", prompt: { text: "again" } })
  await h.hooks.context!(event)
  await settle()
  assert.deepEqual(h.switched, [])
})

test("evicts only the llama.cpp slot that served this OpenCode session", async () => {
  const erased: string[] = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async (input: any) => {
    const url = String(input)
    if (url.endsWith("/slots")) {
      return new Response(JSON.stringify([{ id: 0, next_token: { n_past: 4_000 } }, { id: 5, next_token: { n_past: 1_200 } }]))
    }
    if (url.includes("?action=erase")) {
      erased.push(url)
      return new Response("{}")
    }
    return new Response("not found", { status: 404 })
  }) as typeof fetch

  try {
    const h = harness({
      config: {
        log: false,
        contextTokens: 100,
        fallback: { providerID: "openrouter", modelID: "deepseek/deepseek-chat-v3.1" },
        local: [{ providerID: "llamacpp", backend: { kind: "llamacpp", baseURL: "http://test:8080" } }],
      },
      model: { providerID: "llamacpp", id: "local-qwen" },
      messages: assistantTurn(9_000),
    })
    await plugin.setup(h.ctx)

    // The server told us this session is served from slot 5.
    await h.hooks["http.response"]!({
      sessionID: "ses_test",
      kind: "primary",
      model: { providerID: "llamacpp", id: "local-qwen" },
      response: new Response('data: {"content":"hi","id_slot":5}\n\n'),
    })
    await settle()

    await h.hooks.context!({
      sessionID: "ses_test",
      model: { providerID: "llamacpp", id: "local-qwen" },
      system: [],
      messages: [],
      options: {},
    })
    await settle()

    assert.deepEqual(erased, ["http://test:8080/slots/5?action=erase"])
  } finally {
    globalThis.fetch = originalFetch
  }
})

test("never touches the server when no slot is attributed to the session", async () => {
  const calls: string[] = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async (input: any) => {
    calls.push(String(input))
    return new Response("{}")
  }) as typeof fetch

  try {
    const h = harness({
      config: {
        log: false,
        contextTokens: 100,
        fallback: { providerID: "openrouter", modelID: "deepseek/deepseek-chat-v3.1" },
        local: [{ providerID: "llamacpp", backend: { kind: "llamacpp", baseURL: "http://test:8080" } }],
      },
      model: { providerID: "llamacpp", id: "local-qwen" },
      messages: assistantTurn(9_000),
    })
    await plugin.setup(h.ctx)

    await h.hooks.context!({
      sessionID: "ses_test",
      model: { providerID: "llamacpp", id: "local-qwen" },
      system: [],
      messages: [],
      options: {},
    })
    await settle()

    assert.deepEqual(calls, [], "a no-op means no requests at all")
    assert.match(h.synthetic.join("\n"), /Nothing to clear locally/)
  } finally {
    globalThis.fetch = originalFetch
  }
})

test("an ollama hand-off never unloads the model", async () => {
  const calls: string[] = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async (input: any) => {
    calls.push(String(input))
    return new Response("{}")
  }) as typeof fetch

  try {
    const h = harness({
      config: {
        log: false,
        contextTokens: 100,
        fallback: { providerID: "openrouter", modelID: "deepseek/deepseek-chat-v3.1" },
        local: [{ providerID: "ollama", backend: { kind: "ollama", baseURL: "http://test:11434" } }],
      },
      model: { providerID: "ollama", id: "deepseek-r1:70b" },
      messages: assistantTurn(9_000),
    })
    await plugin.setup(h.ctx)

    await h.hooks.context!({
      sessionID: "ses_test",
      model: { providerID: "ollama", id: "deepseek-r1:70b" },
      system: [],
      messages: [],
      options: {},
    })
    await settle()

    assert.deepEqual(calls, [], "no /api/generate keep_alive=0, no /api/ps")
    assert.equal(h.switched.length, 1)
    assert.match(h.synthetic.join("\n"), /Nothing to clear locally: no per-session cache API in Ollama/)
  } finally {
    globalThis.fetch = originalFetch
  }
})

test("re-reads the config file when it changes on disk", async () => {
  const dir = mkdtempSync(join(tmpdir(), "smart-router-"))
  const file = join(dir, "router.json")
  writeFileSync(file, JSON.stringify(baseConfig))

  const h = harness({ configPath: file, messages: assistantTurn(9_000) })
  await plugin.setup(h.ctx)
  const event = { sessionID: "ses_test", model: localModel, system: [], messages: [], options: {} }

  await h.hooks.context!(event)
  await settle()
  assert.equal(h.switched.length, 1)

  writeFileSync(file, JSON.stringify({ ...baseConfig, contextTokens: 20_000 }))
  utimesSync(file, new Date(), new Date(Date.now() + 2_000))

  h.switched.length = 0
  h.select(localModel)
  await h.hooks.context!(event)
  await settle()
  assert.equal(h.switched.length, 0, "raised threshold applies without reloading the plugin")
})

test("fallback auto picks a deepseek model over the provider's first entry", async () => {
  const h = harness({ config: baseConfig, messages: assistantTurn(9_000) })
  await plugin.setup(h.ctx)
  await h.hooks.context!({ sessionID: "ses_test", model: localModel, system: [], messages: [], options: {} })
  await settle()
  assert.equal(h.switched[0]?.id, "deepseek/deepseek-chat-v3.1")
})
