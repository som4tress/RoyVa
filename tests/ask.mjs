// Ask one or more prompts through the same OpenCode session API the Telegram bridge uses. No Telegram involved.
// Usage: . scripts/env.sh; node tests/ask.mjs "prompt 1" "prompt 2"
import { openCodeAPI, runText } from '../bridge/opencode.mjs';

process.env.OPENCODE_TG_URL ||= `http://127.0.0.1:${process.env.ROYVA_PORT_OPENCODE || 49380}`;
const dir = process.env.OPENCODE_TG_DIR || '/home/somdutta/RoyVa/runtime/workspace';

for (const prompt of process.argv.slice(2)) {
  const t0 = Date.now();
  const session = await openCodeAPI('/api/session', 'POST', { location: { directory: dir } });
  let answer;
  try { answer = await runText(session.id, prompt); } catch (e) { answer = `ERROR: ${e.message}`; }
  const msgs = await openCodeAPI(`/api/session/${session.id}/message`);
  const tools = [];
  for (const m of msgs) for (const p of (m.content ?? [])) if (p.type && p.type !== 'text') tools.push(p.name || p.tool || p.type);
  console.log(JSON.stringify({ prompt, session: session.id, secs: +((Date.now() - t0) / 1000).toFixed(1), parts: tools, answer: answer.slice(0, 600) }, null, 1));
}
