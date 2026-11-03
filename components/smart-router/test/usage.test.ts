import assert from "node:assert/strict"
import { test } from "node:test"
import { contextTokens, estimateTokens, usageFromMessages, usageFromRequest } from "../src/usage.ts"

const user = (text: string) => ({ type: "user", content: [{ type: "text", text }] })
const assistant = (tokens: object, text = "") => ({ type: "assistant", content: [{ type: "text", text }], tokens })

test("context tokens sum prompt, cache and generated output", () => {
  assert.equal(contextTokens({ input: 100, output: 20, cache: { read: 1000, write: 50 } }), 1170)
})

test("reasoning tokens are excluded unless asked for", () => {
  assert.equal(contextTokens({ input: 10, output: 5, reasoning: 900 }), 15)
  assert.equal(contextTokens({ input: 10, output: 5, reasoning: 900 }, true), 915)
})

test("the newest assistant message reports the live context size", () => {
  const messages = [
    user("hello"),
    assistant({ input: 100, output: 10, cache: { read: 0, write: 0 } }),
    user("again"),
    assistant({ input: 2_000, output: 120, cache: { read: 30_000, write: 0 } }),
  ]
  const usage = usageFromMessages(messages)
  assert.equal(usage.tokens, 32_120)
  assert.equal(usage.loops, 1, "only one model call in the current turn")
  assert.equal(usage.measured, true)
})

test("loops count every model call since the last user message", () => {
  const messages = [
    user("do a thing"),
    assistant({ input: 10, output: 1 }),
    assistant({ input: 20, output: 1 }),
    assistant({ input: 30, output: 1 }),
  ]
  assert.equal(usageFromMessages(messages).loops, 3)
})

test("falls back to a character estimate when the server reports no usage", () => {
  const messages = [user("x".repeat(3600))]
  const usage = usageFromMessages(messages)
  assert.equal(usage.measured, false)
  assert.ok(usage.tokens >= 1000 && usage.tokens <= 1030, `got ${usage.tokens}`)
})

test("estimateTokens handles structures and strings", () => {
  assert.equal(estimateTokens("a".repeat(36)), 10)
  assert.ok(estimateTokens({ a: "b".repeat(100) }) > 20)
  assert.equal(estimateTokens(undefined), 0)
})

test("usageFromRequest measures the outgoing request", () => {
  const usage = usageFromRequest([user("hello there")], [{ type: "text", text: "be nice" }])
  assert.equal(usage.measured, false)
  assert.ok(usage.tokens > 0)
})
