// Does a per-session `permissions` list control which tools the model receives, and can PATCH widen it mid-session?
// Reads tool lists from the proxy captures (captures/index.jsonl). Read-only prompts only.
import { readFileSync } from 'node:fs';
import { openCodeAPI, runText } from '../bridge/opencode.mjs';

process.env.OPENCODE_TG_URL ||= `http://127.0.0.1:${process.env.ROYVA_PORT_OPENCODE || 49380}`;
const dir = '/home/somdutta/RoyVa/runtime/workspace';
const allow = names => names.map(action => ({ action, resource: '*', effect: 'allow' }));
const lastToolNames = () => {
  const rows = readFileSync('/home/somdutta/RoyVa/captures/index.jsonl', 'utf8').trim().split('\n').map(l => JSON.parse(l)).filter(r => r.type === 'req' && r.n_tools > 0);
  return rows.at(-1)?.tool_names ?? [];
};
const HA = ['home-assistant_homeassistant__GetLiveContext', 'home-assistant_llm__GetDateTime'];
const MAIL = ['gmail_list_messages', 'gmail_search_messages', 'gmail_read_message', 'gmail_list_labels'];

async function probe(label, sessionId, text) {
  await runText(sessionId, text);
  console.log(`${label}: tools the model received -> ${JSON.stringify(lastToolNames())}`);
}

const a = await openCodeAPI('/api/session', 'POST', { location: { directory: dir }, agent: 'royva', permissions: allow(HA) });
await probe('A  (HA read only)       ', a.id, 'Reply with the single word OK.');

const b = await openCodeAPI('/api/session', 'POST', { location: { directory: dir }, agent: 'royva', permissions: allow(MAIL) });
await probe('B  (Gmail read only)    ', b.id, 'Reply with the single word OK.');

const c = await openCodeAPI('/api/session', 'POST', { location: { directory: dir }, agent: 'royva' });
await probe('C  (no session grants)  ', c.id, 'Reply with the single word OK.');

await openCodeAPI(`/api/session/${a.id}`, 'PATCH', { permissions: allow([...HA, 'websearch', 'webfetch']) });
await probe('A2 (A widened by PATCH) ', a.id, 'Reply with the single word OK again.');
