import { setTimeout } from 'node:timers/promises';

export async function openCodeAPI(path, method = 'GET', body) {
  const response = await fetch(`${process.env.OPENCODE_TG_URL}${path}`, {
    method,
    headers: { 'content-type': 'application/json', authorization: `Basic ${Buffer.from(`opencode:${process.env.OPENCODE_SERVER_PASSWORD}`).toString('base64')}` },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error(`OpenCode HTTP ${response.status}`);
  if (response.status === 204) return;
  const value = await response.json();
  return value?.data ?? value;
}

export async function runText(sessionID, text, { api = openCodeAPI, signal, onPermission = async () => {}, onProgress = async () => {} } = {}) {
  const path = `/api/session/${encodeURIComponent(sessionID)}`;
  const before = await api(`${path}/message`);
  const known = new Set(before.map(message => message.id));
  await api(`${path}/prompt`, 'POST', { text, delivery: 'queue' });
  const announced = new Set();
  const deadline = Date.now() + 15 * 60 * 1000;
  while (!signal?.aborted && Date.now() < deadline) {
    const [messages, session, permissions] = await Promise.all([
      api(`${path}/message`), api(path), api(`${path}/permission`),
    ]);
    for (const permission of permissions) {
      if (announced.has(permission.id)) continue;
      announced.add(permission.id);
      await onPermission(permission);
    }
    const rows = messages.filter(message => !known.has(message.id)).sort((a, b) => a.time.created - b.time.created);
    await onProgress(rows);
    const user = rows.find(message => message.type === 'user');
    if (user && session.time.idle >= user.time.created && session.time.idle >= (session.time.busy || 0)) {
      const assistants = rows.filter(message => message.type === 'assistant');
      const last = assistants.at(-1);
      if (last?.error) throw new Error(`OpenCode: ${JSON.stringify(last.error)}`);
      const answer = assistants.flatMap(message => message.content.filter(part => part.type === 'text').map(part => part.text)).join('\n\n').trim();
      return answer || 'OpenCode finished without a text response.';
    }
    await setTimeout(500, undefined, { signal }).catch(error => { if (error.name !== 'AbortError') throw error; });
  }
  await api(`${path}/interrupt`, 'POST', {});
  return signal?.aborted ? 'Stopped.' : 'OpenCode timed out. The session is preserved; reply to continue.';
}

export function replySession(state, message) {
  return message.reply_to_message && state.messages[`${message.chat.id}:${message.reply_to_message.message_id}`];
}
