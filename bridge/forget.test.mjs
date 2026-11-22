import test from 'node:test';
import assert from 'node:assert/strict';
import { trackMessages, messagesOfSession, deleteMessages } from './forget.mjs';

test('every message of a conversation is found: the user\'s, the answers, the status bar, pictures, permission requests', () => {
  const state = { messages: {}, answers: {}, permissions: {} };
  trackMessages(state, 5, [10, 11], 'ses_A');                                   // the question and a steering reply
  trackMessages(state, 5, [12], 'ses_A');                                       // the live status message
  state.answers['5:13'] = { sessionID: 'ses_A', assistantIDs: ['x'] };          // the answer with the Forget button
  state.permissions['5:14'] = { sessionID: 'ses_A', requestID: 'r' };           // a permission request
  trackMessages(state, 5, [20, 21], 'ses_B');                                   // another conversation
  const a = messagesOfSession(state, 'ses_A').map(m => `${m.chatId}:${m.messageId}`).sort();
  assert.deepEqual(a, ['5:10', '5:11', '5:12', '5:13', '5:14']);
  assert.deepEqual(messagesOfSession(state, 'ses_B').map(m => m.messageId).sort(), [20, 21]);
  assert.deepEqual(messagesOfSession(state, 'ses_none'), []);
});

test('a message known in two places is listed once, and ids are numbers', () => {
  const state = { messages: { '5:13': 'ses_A' }, answers: { '5:13': { sessionID: 'ses_A' } }, permissions: {} };
  assert.deepEqual(messagesOfSession(state, 'ses_A'), [{ chatId: 5, messageId: 13 }]);
});

test('tracking ignores missing ids and empty lists', () => {
  const state = { messages: {}, answers: {}, permissions: {} };
  trackMessages(state, 5, [undefined, null, 0, 7], 'ses_A'); trackMessages(state, 5, undefined, 'ses_A'); trackMessages(state, 5, [8], '');
  assert.deepEqual(Object.keys(state.messages), ['5:7']);
});

test('deleting asks Telegram to delete each message and counts what it could not (older than 48 hours, already gone)', async () => {
  const calls = [];
  const tg = async (method, args) => { calls.push([method, args.chat_id, args.message_id]); if (args.message_id === 2) throw new Error("Bad Request: message can't be deleted for everyone"); return true; };
  const r = await deleteMessages(tg, [{ chatId: 5, messageId: 1 }, { chatId: 5, messageId: 2 }, { chatId: 5, messageId: 3 }]);
  assert.deepEqual(r, { deleted: 2, failed: 1 }); assert.deepEqual(calls.map(c => c[0]), ['deleteMessage', 'deleteMessage', 'deleteMessage']);
  assert.deepEqual(calls.map(c => c[2]).sort(), [1, 2, 3]);
});

test('deleting nothing is fine', async () => {
  assert.deepEqual(await deleteMessages(async () => { throw new Error('should not be called'); }, []), { deleted: 0, failed: 0 });
});
