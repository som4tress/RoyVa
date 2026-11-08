// Serial, repeatable suite over the Telegram path. Each prompt is injected (mirrored into the owner's chat), then we wait for
// the new OpenCode session to go idle, and record tool use / answer / proxy stats for that window.
// Usage: node tests/suite.mjs <label> [reps=3] [promptIds=P1,P2,...]
import { readFileSync, writeFileSync, mkdirSync, appendFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { openCodeAPI } from '../bridge/opencode.mjs';

process.env.OPENCODE_TG_URL ||= `http://127.0.0.1:${process.env.ROYVA_PORT_OPENCODE || 49380}`;
const R = '/home/somdutta/RoyVa';
const INJECT = join(R, 'runtime/inject');
const [label = 'run', repsArg = '3', onlyArg = ''] = process.argv.slice(2);
const reps = Number(repsArg);
const only = onlyArg ? onlyArg.split(',') : null;

const HA = /GetLiveContext|GetDateTime/, MAIL = /^gmail_/, WEB = /^(websearch|webfetch)$/;
const CODING = /^(read|glob|grep|shell|edit|write|subagent|execute|skill)$/;
const PROMPTS = [
  { id: 'P1', text: 'What is the status of lights upstairs?', want: HA },
  { id: 'P2', text: 'How much distance has my mustang travelled this week?', want: HA },
  { id: 'P3', text: 'What is the weather forecast for the next 10 days?', want: WEB },
  { id: 'P4', text: 'What is the weather inside and outside of my house?', want: HA, wantAlso: WEB },
  { id: 'P5', text: 'List the top 20 oldest unread emails from my gmail.', want: MAIL },
  { id: 'P6', text: 'Find any email that has mention of "XYZ".', want: MAIL },
].filter(p => !only || only.includes(p.id));
const REFUSAL = /(don'?t|do not|cannot|can'?t|unable to|no) (have )?(any )?(access|tool|way)|not able to (access|check)/i;

const sleep = ms => new Promise(r => setTimeout(r, ms));
const listSessions = async () => { const s = await openCodeAPI('/api/session'); return Array.isArray(s) ? s : (s.sessions || []); };
const isIdle = s => s.time && s.time.idle != null && s.time.idle >= (s.time.busy || 0);

function proxyWindow(t0, t1) {
  const f = join(R, 'captures/index.jsonl'); if (!existsSync(f)) return {};
  const rows = readFileSync(f, 'utf8').trim().split('\n').map(l => JSON.parse(l));
  const resp = new Map(rows.filter(r => r.type === 'resp').map(r => [r.id, r]));
  const reqs = rows.filter(r => r.type === 'req' && r.ts && Date.parse(r.ts) >= t0 - 500 && Date.parse(r.ts) <= t1 + 500 && r.n_tools > 0);
  return { llm_requests: reqs.length, max_prompt_tokens: Math.max(0, ...reqs.map(r => resp.get(r.id)?.usage?.prompt_tokens || 0)), ids: reqs.map(r => r.id) };
}

mkdirSync(join(R, 'runtime/results'), { recursive: true });
const out = join(R, `runtime/results/${label}.jsonl`);
const all = [];
for (let rep = 1; rep <= reps; rep++) {
  for (const p of PROMPTS) {
    const before = new Set((await listSessions()).map(s => s.id));
    const t0 = Date.now();
    writeFileSync(join(INJECT, `${t0}-${p.id}.json`), JSON.stringify({ label: `${label} ${p.id} #${rep}`, text: p.text }), { mode: 0o600 });
    let sid = null, status = 'ok';
    while (Date.now() - t0 < 300000) {
      await sleep(1500);
      const now = await listSessions();
      sid ||= now.find(s => !before.has(s.id))?.id ?? null;
      const s = sid && now.find(x => x.id === sid);
      if (s && isIdle(s) && Date.now() - t0 > 4000) break;
    }
    if (Date.now() - t0 >= 300000) { status = 'timeout'; if (sid) await openCodeAPI(`/api/session/${sid}/interrupt`, 'POST', {}).catch(() => {}); await sleep(2000); }
    const t1 = Date.now();
    const msgs = sid ? await openCodeAPI(`/api/session/${sid}/message`) : [];
    const tools = []; let answer = '';
    for (const m of msgs) for (const part of (m.content ?? [])) {
      if (part.type === 'text' && m.type === 'assistant') answer = part.text;
      else if (part.type && part.type !== 'text' && m.type === 'assistant') tools.push(part.name || part.tool || part.type);
    }
    const win = proxyWindow(t0, t1);
    const rec = {
      label, rep, id: p.id, status, session: sid, secs: +((t1 - t0) / 1000).toFixed(1), tools, ...win,
      called_expected: tools.some(t => p.want.test(t)) && (!p.wantAlso || tools.some(t => p.wantAlso.test(t)) || tools.some(t => p.want.test(t))),
      refusal: tools.length === 0 && REFUSAL.test(answer),
      coding_tool_use: tools.some(t => CODING.test(t)),
      loop: (win.llm_requests || 0) > 10,
      answer: answer.slice(0, 700),
    };
    appendFileSync(out, JSON.stringify(rec) + '\n', { mode: 0o600 });
    all.push(rec);
    console.log(`${label} ${p.id}#${rep} ${rec.status} ${rec.secs}s reqs=${rec.llm_requests} tok=${rec.max_prompt_tokens} tools=${tools.length} expected=${rec.called_expected} refusal=${rec.refusal} coding=${rec.coding_tool_use} loop=${rec.loop}`);
    await sleep(1500);
  }
}
console.log('\n=== SUMMARY', label, '===');
console.log('prompt  runs  called_expected  refusal  coding_tools  loop  avg_secs  avg_reqs  max_tok');
for (const p of PROMPTS) {
  const rs = all.filter(r => r.id === p.id), n = rs.length, pc = k => `${Math.round(rs.filter(r => r[k]).length / n * 100)}%`.padStart(4);
  console.log(`${p.id.padEnd(6)} ${String(n).padStart(4)}  ${pc('called_expected').padStart(14)}  ${pc('refusal').padStart(7)}  ${pc('coding_tool_use').padStart(11)}  ${pc('loop').padStart(4)}  ${(rs.reduce((a, r) => a + r.secs, 0) / n).toFixed(0).padStart(8)}  ${(rs.reduce((a, r) => a + (r.llm_requests || 0), 0) / n).toFixed(1).padStart(8)}  ${Math.max(...rs.map(r => r.max_prompt_tokens || 0)).toString().padStart(7)}`);
}
