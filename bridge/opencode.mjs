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

// A request gets RUN_LIMIT_MS in total. A picture or video tool can legitimately run for many minutes (a 2-minute video takes about 17), so once such a tool has been seen in the run the limit becomes MEDIA_RUN_LIMIT_MS. It never shrinks again, so the model still has time to write its reply after a long tool call.
export const RUN_LIMIT_MS = 15 * 60 * 1000, MEDIA_RUN_LIMIT_MS = 45 * 60 * 1000;
const MEDIA_TOOL = /generate_video|generate_image_set|generate_image|edit_image/;
export function runLimitMs(rows, current = RUN_LIMIT_MS) {
  const media = rows.some(message => (message.content ?? []).some(part => part.type === 'tool' && MEDIA_TOOL.test(part.name ?? '')));
  return Math.max(current, media ? MEDIA_RUN_LIMIT_MS : RUN_LIMIT_MS);
}

export async function runText(sessionID, text, { api = openCodeAPI, signal, files = [], onPermission = async () => {}, onProgress = async () => {}, onBeforeFinish = async () => false, onAdmitted = async () => {} } = {}) {
  const path = `/api/session/${encodeURIComponent(sessionID)}`;
  const before = await api(`${path}/message`);
  const known = new Set(before.map(message => message.id));
  await api(`${path}/prompt`, 'POST', { text, delivery: 'queue', ...(files.length ? {files} : {}) });
  await onAdmitted();
  const announced = new Set();
  const started = Date.now();
  let limit = RUN_LIMIT_MS;
  while (!signal?.aborted && Date.now() - started < limit) {
    const [messages, session, permissions] = await Promise.all([
      api(`${path}/message`), api(path), api(`${path}/permission`),
    ]);
    const rows = messages.filter(message => !known.has(message.id)).sort((a, b) => a.time.created - b.time.created);
    limit = runLimitMs(rows, limit);
    await onProgress(rows);
    for (const permission of permissions) {
      if (announced.has(permission.id)) continue;
      await onPermission(permission, messages);
      announced.add(permission.id);
    }
    const user = rows.filter(message => message.type === 'user').at(-1);
    if (user && session.time.idle >= user.time.created && session.time.idle >= (session.time.busy || 0)) {
      if (await onBeforeFinish()) continue;
      const assistants = rows.filter(message => message.type === 'assistant');
      const last = assistants.at(-1);
      if (last?.error) throw new Error(`OpenCode: ${JSON.stringify(last.error)}`);
      const answer = (last?.content ?? []).filter(part => part.type === 'text').map(part => part.text).join('\n\n').trim();
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

export async function steerText(sessionID, text, {api = openCodeAPI, files = []} = {}) {
  return api(`/api/session/${encodeURIComponent(sessionID)}/prompt`, 'POST', {text, delivery: 'steer', ...(files.length ? {files} : {})});
}
