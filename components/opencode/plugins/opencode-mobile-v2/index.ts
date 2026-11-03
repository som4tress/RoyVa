// OpenCode V2 compatibility wrapper for the V1-only `opencode-mobile` plugin.
//
// Upstream: https://github.com/doza62/opencode-mobile (npm: opencode-mobile@1.4.0)
// The upstream package still default-exports a V1-style async plugin function,
// which OpenCode v2 rejects ("Plugin must export a default definition with an id
// and an effect or setup function" — see upstream issue #37). This wrapper loads
// the V1 module from OpenCode's plugin cache and adapts it to the V2 API:
//
//   - V1 returned hooks { tool: { mobile }, event }  ->
//       V2 ctx.tool.transform() for the tool and ctx.event.subscribe() for events.
//
// The wrapper stays out of the way: the V1 plugin itself gates its LAN server and
// tunnel on `opencode serve` mode, so under the TUI/background service it only
// provides the `mobile` tool.

import { existsSync, readdirSync, statSync } from "node:fs"
import { homedir } from "node:os"
import path from "node:path"
import { pathToFileURL } from "node:url"

type V1MobileTool = {
  description?: string
  execute: (args: Record<string, unknown>, context?: unknown) => Promise<unknown>
}

type V1Hooks = {
  tool?: { mobile?: V1MobileTool }
  event?: (input: { event: unknown }) => Promise<void> | void
}

// Locate the newest opencode-mobile install inside OpenCode's npm plugin cache.
// The cache directory contains a timestamped hash folder per install, so resolve
// dynamically instead of hard-coding the path.
function resolveV1Entrypoint(): string | undefined {
  const base = path.join(homedir(), ".cache", "opencode", "npm", "opencode-mobile@latest")
  if (!existsSync(base)) return undefined
  let best: { file: string; mtime: number } | undefined
  for (const entry of readdirSync(base)) {
    const candidate = path.join(base, entry, "node_modules", "opencode-mobile", "dist", "index.js")
    if (!existsSync(candidate)) continue
    const mtime = statSync(candidate).mtimeMs
    if (!best || mtime > best.mtime) best = { file: candidate, mtime }
  }
  return best?.file
}

let hooks: V1Hooks | undefined

export default {
  id: "opencode-mobile",
  async setup(ctx: any) {
    const entry = resolveV1Entrypoint()
    if (!entry) {
      console.error(
        "[opencode-mobile-v2] Could not find opencode-mobile in the OpenCode plugin cache. " +
          "Run `opencode plugin add opencode-mobile@latest`, then use /reload to restore it.",
      )
      return
    }

    // Load the V1 plugin and run its setup against the V2 context. It only reads
    // optional ctx.client / ctx.serverUrl, so the V2 context is safe to pass.
    const mod: any = await import(pathToFileURL(entry).href)
    const v1Plugin = mod.default as (c: unknown) => Promise<V1Hooks>
    hooks = (await v1Plugin({ ...ctx, serverUrl: new URL("http://127.0.0.1:49374") })) ?? {}
    console.log(
      "[opencode-mobile-v2] Loaded V1 opencode-mobile (" +
        (hooks.tool?.mobile ? "mobile tool found" : "no mobile tool") +
        ")",
    )

    // Register the V1 "mobile" tool through the V2 tool registry.
    const mobile = hooks.tool?.mobile
    if (mobile) {
      await ctx.tool.transform((editor: any) => {
        editor.add({
          name: "mobile",
          description: mobile.description ?? "Generate a mobile connection QR code",
          input: {
            type: "object",
            properties: {
              url: { type: "string", description: "Tunnel URL to render as a QR code" },
              tunnelPath: { type: "string", description: "Path to a tunnel.json containing a URL" },
              token: {
                type: "string",
                description:
                  "Expo push token to register, optionally followed by a server URL " +
                  "(ExponentPushToken[xxx] ServerUrl[http://...])",
              },
            },
            additionalProperties: false,
          },
          execute: async (input: Record<string, unknown>) => {
            const result = await mobile.execute(input ?? {})
            return { content: typeof result === "string" ? result : JSON.stringify(result) }
          },
        })
      })
    }

    // Forward V2 server events to the V1 event hook. The V1 handler is a no-op
    // unless OpenCode is running in `opencode serve` mode.
    const handler = hooks.event
    if (handler) {
      const controller = new AbortController()
      void (async () => {
        try {
          for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
            try {
              await handler({ event })
            } catch (error) {
              console.error("[opencode-mobile-v2] V1 event handler error:", error)
            }
          }
        } catch (error) {
          if (!controller.signal.aborted) {
            console.error("[opencode-mobile-v2] event subscription error:", error)
          }
        }
      })()
      return () => controller.abort()
    }
  },
}
