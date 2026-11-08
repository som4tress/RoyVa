import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { UsageTotals, formatFinalUsage, tokenUsage } from './usage.mjs';

const row = (id, input, cacheRead, output, reasoning = 0) => ({ type: 'assistant', id, tokens: { input, output, reasoning, cache: { read: cacheRead } } });
const file = () => join(mkdtempSync(join(tmpdir(), 'usage-')), 'u.json');

test('input includes cached; uncached is the difference', () => {
  const u = tokenUsage([row('m1', 100, 900, 50)]);
  assert.equal(u.input, 1000); assert.equal(u.cached, 900); assert.equal(u.output, 50);
});

test('lifetime totals persist across restarts and never double-count a session', () => {
  const f = file();
  let t = new UsageTotals(f);
  t.record('s1', [row('m1', 10, 0, 5)]);
  t.record('s1', [row('m1', 10, 0, 5), row('m2', 20, 100, 7)]);        // reply in the same session: only m2 is new
  t = new UsageTotals(f);                                              // "restart"
  t.record('s2', [row('m3', 1, 0, 1)]);
  assert.deepEqual([t.lifetime.input, t.lifetime.cached, t.lifetime.output, t.lifetime.runs], [10 + 120 + 1, 100, 5 + 7 + 1, 3]);
});

test('a corrupt file starts fresh instead of crashing', () => {
  const f = file(); writeFileSync(f, '{broken');
  const t = new UsageTotals(f); t.record('s', [row('m1', 1, 0, 1)]);
  assert.equal(new UsageTotals(f).lifetime.input, 1);
});

test('final footer shows this request and all-time with cached/uncached', () => {
  const run = tokenUsage([row('m1', 100, 900, 50, 10)]);
  const out = formatFinalUsage(run, { input: 5000, cached: 4000, output: 300, reasoning: 0, passes: 9, runs: 4 }, '2026-11-08T00:00:00Z');
  assert.match(out, /This request: in 1,000 \(cached 900 · uncached 100\) · out 50/);
  assert.match(out, /All time \(since 2026-11-08\): in 5,000 \(cached 4,000 · uncached 1,000\) · out 300 · 5,300 total · 4 requests/);
});
