import { readFileSync, writeFileSync, renameSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

export function tokenUsage(messages, afterId = '') {
  return messages.filter(message => message.type === 'assistant' && String(message.id || '') > afterId).reduce((sum, message) => {
    const tokens = message.tokens;
    if (!tokens) return sum;
    sum.input += Number(tokens.input || 0) + Number(tokens.cache?.read || 0);
    sum.cached += Number(tokens.cache?.read || 0);
    sum.output += Number(tokens.output || 0);
    sum.reasoning += Number(tokens.reasoning || 0);
    sum.passes++;
    sum.peak = Math.max(sum.peak, Number(tokens.input || 0) + Number(tokens.cache?.read || 0));
    return sum;
  }, { input: 0, cached: 0, output: 0, reasoning: 0, passes: 0, peak: 0 });
}

export function formatUsage(usage) {
  const number = value => value.toLocaleString('en-US');
  return `Tokens: in ${number(usage.input)} (${number(usage.cached)} cached) · out ${number(usage.output)}${usage.reasoning ? ` · think ${number(usage.reasoning)}` : ''} · passes ${usage.passes} · peak input ${number(usage.peak)}`;
}

const fmt = value => Number(value || 0).toLocaleString('en-US');

// Lifetime totals survive restarts: one small JSON file, written atomically. Per-session watermarks (message ids are ascending)
// stop a reply inside an old session from counting that session's earlier turns twice.
export class UsageTotals {
  constructor(file) { this.file = file; this.data = this.#load(); }
  #load() {
    try { return JSON.parse(readFileSync(this.file, 'utf8')); }
    catch { return { since: new Date().toISOString(), totals: { input: 0, cached: 0, output: 0, reasoning: 0, passes: 0, runs: 0 }, watermarks: {} }; }
  }
  record(sessionID, rows) {
    const mark = this.data.watermarks[sessionID] || '';
    const run = tokenUsage(rows, mark);
    const t = this.data.totals;
    for (const key of ['input', 'cached', 'output', 'reasoning', 'passes']) t[key] += run[key];
    if (run.passes) { t.runs++; this.data.watermarks[sessionID] = rows.filter(r => r.type === 'assistant' && r.tokens).map(r => String(r.id)).sort().at(-1); }
    const keys = Object.keys(this.data.watermarks);
    if (keys.length > 2000) for (const k of keys.slice(0, keys.length - 2000)) delete this.data.watermarks[k];
    this.#save();
    return run;
  }
  #save() {
    try { mkdirSync(dirname(this.file), { recursive: true }); const tmp = `${this.file}.tmp`; writeFileSync(tmp, JSON.stringify(this.data), { mode: 0o600 }); renameSync(tmp, this.file); }
    catch (error) { console.error('Could not save usage totals:', error.message); }
  }
  get lifetime() { return this.data.totals; }
  get since() { return this.data.since; }
}

export function formatFinalUsage(run, totals, since) {
  const line = u => `in ${fmt(u.input)} (cached ${fmt(u.cached)} · uncached ${fmt(u.input - u.cached)}) · out ${fmt(u.output)}${u.reasoning ? ` (of which thinking ${fmt(u.reasoning)})` : ''}`;
  return `\n\n— Tokens —\nThis request: ${line(run)} · ${run.passes} model passes\nAll time (since ${String(since).slice(0, 10)}): ${line(totals)} · ${fmt(totals.input + totals.output)} total · ${fmt(totals.runs)} requests`;
}

export async function streamingTokens(text) {
  if (!text) return 0;
  const response = await fetch('http://127.0.0.1:8000/tokenize', {
    method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${process.env.VLLM_API_KEY}` },
    body: JSON.stringify({ content: text, add_special: false }), signal: AbortSignal.timeout(3000),
  });
  if (!response.ok) return null;
  return (await response.json()).tokens.length;
}
