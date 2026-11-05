import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runText, replySession } from './opencode.mjs';

test('only a reply within the same chat resumes a session', () => {
  const state = { messages: { '1:7': 'session-a', '2:7': 'session-b' } };
  assert.equal(replySession(state, { chat: { id: 1 }, message_id: 8 }), undefined);
  assert.equal(replySession(state, { chat: { id: 1 }, reply_to_message: { message_id: 7 } }), 'session-a');
  assert.equal(replySession(state, { chat: { id: 2 }, reply_to_message: { message_id: 7 } }), 'session-b');
});

test('native admission preserves exact text and excludes earlier answers', async () => {
  const calls = [];
  const permissionNotices = [];
  const text = '- Keep my message exactly.\nNo added prompt.';
  const api = async (path, method, body) => {
    calls.push({ path, method, body });
    if (method === 'POST') return;
    if (path.endsWith('/permission')) return [{ id: 'per_1', action: 'shell', resources: ['example'] }];
    if (!path.endsWith('/message')) return { time: { idle: 5, busy: 2 } };
    const old = { id: 'old', type: 'assistant', time: { created: 1 }, content: [{ type: 'text', text: 'old answer' }] };
    if (calls.length === 1) return [old];
    // API order is newest-first and includes non-conversation records.
    return [{ id: 'idle', type: 'idle', time: { created: 5 } }, { id: 'answer', type: 'assistant', time: { created: 4 }, content: [{ type: 'text', text: 'new answer' }] }, { id: 'user', type: 'user', time: { created: 3 }, text }, old];
  };
  assert.equal(await runText('ses_test', text, { api, onPermission: async permission => permissionNotices.push(permission.id) }), 'new answer');
  assert.deepEqual(calls.filter(call => call.method === 'POST'), [{ path: '/api/session/ses_test/prompt', method: 'POST', body: { text, delivery: 'queue' } }]);
  assert.deepEqual(permissionNotices, ['per_1']);
});

test('interruption stops native execution without replaying the prompt', async () => {
  const controller = new AbortController();
  controller.abort();
  const calls = [];
  const api = async (path, method, body) => { calls.push({ path, method, body }); return []; };
  assert.equal(await runText('ses_test', 'hello', { api, signal: controller.signal }), 'Stopped.');
  assert.equal(calls.filter(call => call.path.endsWith('/interrupt')).length, 1);
  assert.equal(calls.filter(call => call.path.endsWith('/prompt')).length, 1);
});

import { tokenUsage, formatUsage } from './usage.mjs';
test('token display includes cached input without counting non-assistant events', () => {
  const usage = tokenUsage([
    { type: 'user', tokens: { input: 999 } },
    { type: 'assistant', tokens: { input: 20, output: 7, cache: { read: 80 } } },
    { type: 'assistant', tokens: { input: 10, output: 3, cache: { read: 100 } } },
    { type: 'assistant' },
  ]);
  assert.deepEqual(usage, { input: 210, cached: 180, output: 10, reasoning: 0, passes: 2, peak: 110 });
  assert.match(formatUsage(usage), /in 210 \(180 cached\).*out 10.*passes 2.*peak input 110/);
});
