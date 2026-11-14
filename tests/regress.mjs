// End-to-end regression suite built from real past queries. No Telegram involved.
// Layer 1 (route): POST /v1/route for each query and check intents/mode/permission grants. Fast, no model turn.
// Layer 2 (live):  cases marked "live" are then run through OpenCode (same runText the bridge uses); any permission
//                  request is DENIED, so nothing can change in the house. Checks tools used and the answer.
// Usage: . scripts/env.sh; node tests/regress.mjs [--live] [--only=id1,id2] [--json=out.json]
import { readFileSync, writeFileSync } from 'node:fs';
import { openCodeAPI, runText } from '../bridge/opencode.mjs';

process.env.OPENCODE_TG_URL ||= `http://127.0.0.1:${process.env.ROYVA_PORT_OPENCODE || 49380}`;
const GATEWAY = process.env.ROYVA_GATEWAY_URL || 'http://127.0.0.1:8300';
const OWNER = process.env.ROYVA_TEST_USER || 'telegram:6064019420';
const args = process.argv.slice(2);
const LIVE = args.includes('--live');
const ONLY = (args.find(a => a.startsWith('--only=')) || '').slice(7).split(',').filter(Boolean);
const JSON_OUT = (args.find(a => a.startsWith('--json=')) || '').slice(7);
const cases = JSON.parse(readFileSync(new URL('./regress_cases.json', import.meta.url), 'utf8')).filter(c => !ONLY.length || ONLY.includes(c.id));

// Always true for every routed session, whatever the question was.
const ALWAYS_DENIED = ['shell', 'edit', 'write', 'read', 'glob', 'grep', 'subagent', 'execute', 'question', 'skill', 'gmail_send_message', 'gmail_send_draft'];
const NEVER_ALLOWED = ['ha-api_ha_write', 'ha-api_ha_edit', 'machine_run_approved', 'machine_remote_run_approved', 'gmail-tidy_tidy_ids', 'gmail-tidy_tidy_matching'];

async function route(text, user, session_id, is_reply) {
  const r = await fetch(`${GATEWAY}/v1/route`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, user, session_id: session_id || null, is_reply: Boolean(is_reply) }), signal: AbortSignal.timeout(180000) });
  if (!r.ok) throw new Error(`gateway HTTP ${r.status}`);
  return r.json();
}
const effects = async sid => { const s = await openCodeAPI(`/api/session/${sid}`); const m = new Map(); for (const p of s.permissions || []) m.set(p.action, p.effect); return m; };
const same = (a, b) => a.length === b.length && a.every(x => b.includes(x));

async function checkRoute(step, routed) {
  const f = [];
  if (routed.kind !== 'run') { f.push(`kind=${routed.kind} (${String(routed.answer || '').slice(0, 80)})`); return f; }
  if (step.intents && !same(routed.intents, step.intents)) f.push(`intents ${JSON.stringify(routed.intents)} want ${JSON.stringify(step.intents)}`);
  if (step.intents_exclude && routed.intents.includes(step.intents_exclude)) f.push(`intents ${JSON.stringify(routed.intents)} must not include ${step.intents_exclude}`);
  if (step.intents_include && !routed.intents.includes(step.intents_include)) f.push(`intents ${JSON.stringify(routed.intents)} lack ${step.intents_include}`);
  if (step.mode && routed.mode !== step.mode) f.push(`mode ${routed.mode} want ${step.mode}`);
  if (step.no_write && Object.keys(routed.write_tools || {}).length) f.push(`write tools granted: ${Object.keys(routed.write_tools).join(',')}`);
  if (step.tools_include && !routed.tools.some(t => t === step.tools_include)) f.push(`tool ${step.tools_include} not granted`);
  const eff = await effects(routed.session_id);
  for (const t of ALWAYS_DENIED) if (eff.has(t) && eff.get(t) !== 'deny') f.push(`${t} is ${eff.get(t)} (must be deny)`);
  for (const t of NEVER_ALLOWED) if (eff.get(t) === 'allow') f.push(`${t} is allow (must ask)`);
  for (const t of step.ask || []) if (eff.get(t) !== 'ask') f.push(`${t} is ${eff.get(t)} (want ask)`);
  for (const t of step.allow || []) if (eff.get(t) !== 'allow') f.push(`${t} is ${eff.get(t)} (want allow)`);
  return f;
}

async function live(step, routed) {
  const f = [], used = [], perms = [];
  const t0 = Date.now();
  let answer = '';
  try {
    answer = await runText(routed.session_id, routed.prompt, {
      onPermission: async p => { perms.push(p.action || p.tool || JSON.stringify(p).slice(0, 60)); await openCodeAPI(`/api/session/${routed.session_id}/permission/${p.id}/reply`, 'POST', { decision: 'reject' }); },
    });
  } catch (e) { f.push(`run failed: ${e.message}`); }
  const msgs = await openCodeAPI(`/api/session/${routed.session_id}/message`);
  for (const m of msgs) for (const p of (m.content ?? [])) if (p.type === 'tool') used.push(p.name || p.tool);
  const errs = msgs.flatMap(m => (m.content ?? []).filter(p => p.type === 'tool' && p.state?.status === 'error').map(p => `${p.name || p.tool}: ${String(p.state?.error || '').slice(0, 80)}`));
  if (!String(answer).trim()) f.push('empty answer');
  if (/ReferenceError|TypeError|Traceback|undefined/.test(answer)) f.push('crash text in answer');
  if (step.tools_used && !used.some(t => new RegExp(step.tools_used, 'i').test(t))) f.push(`no tool matching /${step.tools_used}/ (used: ${[...new Set(used)].join(',') || 'none'})`);
  if (step.no_domain_arg) for (const m of msgs) for (const p of (m.content ?? [])) if (p.type === 'tool' && /GetLiveContext|get_live_context/.test(p.name || p.tool || '') && p.state?.input?.domain) f.push(`live-context call filtered by domain: ${JSON.stringify(p.state.input)}`);
  if (step.no_tools_used && used.length) f.push(`used tools: ${[...new Set(used)].join(',')}`);
  if (step.answer_match && !new RegExp(step.answer_match, 'i').test(answer)) f.push(`answer lacks /${step.answer_match}/`);
  if (step.answer_not && new RegExp(step.answer_not, 'i').test(answer)) f.push(`answer matches /${step.answer_not}/`);
  if (perms.length && !step.ask && !(step.expect_permission)) f.push(`unexpected permission request: ${perms.join(',')}`);
  return { f, secs: ((Date.now() - t0) / 1000).toFixed(0), answer: String(answer).slice(0, 160).replace(/\s+/g, ' '), errs };
}

const results = [];
for (const c of cases) {
  const steps = c.seq || [c];
  let sid = null, fails = [], note = '';
  for (const [i, step] of steps.entries()) {
    try {
      const routed = await route(step.q, OWNER, sid, step.reply);
      sid = routed.session_id;
      const tag = steps.length > 1 ? `[step ${i + 1}] ` : '';
      for (const m of await checkRoute(step, routed)) fails.push(tag + m);
      if (LIVE && step.live && routed.kind === 'run') {
        const r = await live(step, routed);
        for (const m of r.f) fails.push(tag + 'live: ' + m);
        note = `${r.secs}s · ${r.answer}${r.errs.length ? ' · tool errors: ' + r.errs.join(' | ') : ''}`;
      }
    } catch (e) { fails.push(`exception: ${e.message}`); }
  }
  const xf = c.xfail ? ' (known issue: ' + c.xfail + ')' : '';
  results.push({ id: c.id, ok: !fails.length, fails, note, xfail: c.xfail || null });
  console.log(`${fails.length ? (c.xfail ? 'XFAIL' : 'FAIL ') : 'ok   '} ${c.id}${fails.length ? ' — ' + fails.join('; ') + xf : ''}${note ? '\n        ' + note : ''}`);
}
// Non-owner must never be given owner doors.
try {
  const r = await route('How much memory is free on this machine?', 'telegram:111111111');
  const bad = (r.tools || []).filter(t => /^(machine|ha_api)\./.test(t));
  const ok = !bad.length;
  results.push({ id: 'non-owner-no-doors', ok, fails: ok ? [] : [`granted ${bad.join(',')}`] });
  console.log(`${ok ? 'ok   ' : 'FAIL '} non-owner-no-doors (kind=${r.kind})${ok ? '' : ' — ' + bad.join(',')}`);
} catch (e) { console.log('ok    non-owner-no-doors (rejected: ' + e.message + ')'); results.push({ id: 'non-owner-no-doors', ok: true, fails: [] }); }
const bad = results.filter(r => !r.ok && !r.xfail);
console.log(`\n${results.length - bad.length}/${results.length} passed, ${results.filter(r => !r.ok && r.xfail).length} known, ${bad.length} failing`);
if (JSON_OUT) writeFileSync(JSON_OUT, JSON.stringify(results, null, 1));
process.exit(bad.length ? 1 : 0);
