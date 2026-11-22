// "Forget this chat" also removes the conversation from Telegram: every message that belongs to a session is remembered (chat id + message id) and deleted with it.
// Telegram lets a bot delete messages in a private chat only within 48 hours of sending; older ones fail and are only counted.
export function trackMessages(state, chatId, ids, sessionID) {
  if (!sessionID || !Array.isArray(ids)) return;
  state.messages ||= {};
  for (const id of ids) if (Number.isInteger(id) && id > 0) state.messages[`${chatId}:${id}`] = sessionID;
}

export function messagesOfSession(state, sessionID) {
  const seen = new Map();
  for (const table of [state.messages, state.answers, state.permissions]) for (const [key, value] of Object.entries(table || {})) {
    if ((typeof value === 'string' ? value : value?.sessionID) !== sessionID) continue;
    const [chat, id] = key.split(':'); if (!chat || !Number.isInteger(Number(id))) continue;
    seen.set(key, { chatId: Number(chat), messageId: Number(id) });
  }
  return [...seen.values()];
}

export async function deleteMessages(tg, list) {
  let deleted = 0, failed = 0;
  for (const m of list) {
    try { await tg('deleteMessage', { chat_id: m.chatId, message_id: m.messageId }); deleted++; } catch { failed++; }
  }
  return { deleted, failed };
}
