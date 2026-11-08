// Logging pass-through in front of llama.cpp. Records every chat request so bugs can cite a capture ID.
// Env: PROXY_PORT (8100), UPSTREAM (http://127.0.0.1:8000), VLLM_API_KEY (injected upstream), CAPTURE_DIR.
import http from 'node:http';
import { mkdirSync, writeFileSync, appendFileSync, createWriteStream } from 'node:fs';
import { join } from 'node:path';

const PORT = Number(process.env.PROXY_PORT || 8100);
const UP = new URL(process.env.UPSTREAM || 'http://127.0.0.1:8000');
const KEY = process.env.VLLM_API_KEY || '';
const DIR = process.env.CAPTURE_DIR || new URL('../captures', import.meta.url).pathname;
mkdirSync(DIR, { recursive: true, mode: 0o700 });
let counter = 0;
const stamp = () => new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
const index = line => appendFileSync(join(DIR, 'index.jsonl'), JSON.stringify(line) + '\n', { mode: 0o600 });

async function tokenCount(text) {
  if (!text) return 0;
  try {
    const r = await fetch(new URL('/tokenize', UP), { method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Bearer ${KEY}` },
      body: JSON.stringify({ content: text }) });
    return (await r.json()).tokens?.length ?? 0;
  } catch { return -1; }
}
const text = c => typeof c === 'string' ? c : Array.isArray(c) ? c.map(p => p.text ?? '').join('') : JSON.stringify(c ?? '');

async function describe(id, body) {
  const msgs = body.messages || [];
  const sys = msgs.filter(m => m.role === 'system').map(m => text(m.content)).join('\n');
  const rest = msgs.filter(m => m.role !== 'system');
  const tools = body.tools || [];
  const [sysTok, toolTok, histTok] = await Promise.all([
    tokenCount(sys), tokenCount(JSON.stringify(tools)), tokenCount(rest.map(m => text(m.content) + JSON.stringify(m.tool_calls ?? '')).join('\n'))]);
  index({ type: 'req', id, ts: new Date().toISOString(), model: body.model, stream: !!body.stream,
    messages: msgs.length, roles: Object.fromEntries(['system', 'user', 'assistant', 'tool'].map(r => [r, msgs.filter(m => m.role === r).length])),
    n_tools: tools.length, tool_names: tools.map(t => t.function?.name),
    tokens: { system: sysTok, tools: toolTok, history: histTok, est_total: sysTok + toolTok + histTok },
    sampling: Object.fromEntries(['temperature', 'top_p', 'top_k', 'min_p', 'presence_penalty', 'max_tokens'].filter(k => k in body).map(k => [k, body[k]])) });
}

function summarizeResponse(id, raw, status, ms) {
  let content = '', reasoning = '', calls = {}, finish = null, usage = null;
  const lines = raw.split('\n').filter(l => l.startsWith('data: ') && !l.includes('[DONE]'));
  const objs = lines.length ? lines.map(l => { try { return JSON.parse(l.slice(6)); } catch { return null; } }) : (() => { try { return [JSON.parse(raw)]; } catch { return []; } })();
  for (const o of objs.filter(Boolean)) {
    if (o.usage) usage = o.usage;
    for (const ch of o.choices || []) {
      const d = ch.delta || ch.message || {};
      content += d.content || '';
      reasoning += d.reasoning_content || '';
      for (const tc of d.tool_calls || []) {
        const k = tc.index ?? Object.keys(calls).length;
        calls[k] ||= { name: '', args: '' };
        calls[k].name += tc.function?.name || '';
        calls[k].args += tc.function?.arguments || '';
      }
      if (ch.finish_reason) finish = ch.finish_reason;
    }
  }
  index({ type: 'resp', id, status, ms, finish, usage, content_chars: content.length, reasoning_chars: reasoning.length,
    content_preview: content.slice(0, 300), tool_calls: Object.values(calls).map(c => ({ name: c.name, args: c.args.slice(0, 300) })) });
}

http.createServer(async (req, res) => {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const body = Buffer.concat(chunks);
  const isChat = req.method === 'POST' && req.url.startsWith('/v1/chat/completions');
  const id = isChat ? `${stamp()}-${String(++counter).padStart(4, '0')}` : null;
  if (isChat) {
    writeFileSync(join(DIR, `${id}.req.json`), body, { mode: 0o600 });
    try { void describe(id, JSON.parse(body.toString())); } catch { index({ type: 'req', id, error: 'unparseable body' }); }
  }
  const t0 = Date.now();
  const headers = { ...req.headers, host: UP.host, authorization: `Bearer ${KEY}` };
  delete headers['content-length'];
  const up = http.request({ host: UP.hostname, port: UP.port, path: req.url, method: req.method, headers: { ...headers, 'content-length': body.length } }, ur => {
    res.writeHead(ur.statusCode, ur.headers);
    const rec = isChat ? [] : null;
    ur.on('data', d => { rec?.push(d); res.write(d); });
    ur.on('end', () => { res.end(); if (rec) { const raw = Buffer.concat(rec).toString(); writeFileSync(join(DIR, `${id}.resp.txt`), raw, { mode: 0o600 }); summarizeResponse(id, raw, ur.statusCode, Date.now() - t0); } });
  });
  up.on('error', e => { if (!res.headersSent) res.writeHead(502); res.end(String(e.message)); });
  res.on('close', () => up.destroy());
  up.end(body);
}).listen(PORT, '127.0.0.1', () => console.log(`royva proxy :${PORT} -> ${UP.origin}, captures in ${DIR}`));
