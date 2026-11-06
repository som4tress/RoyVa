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


test('final reply excludes tool-step narration and preserves all final text parts', async () => {
  let admitted = false;
  const api = async (path, method) => {
    if (method === 'POST') { admitted = true; return; }
    if (path.endsWith('/permission')) return [];
    if (!path.endsWith('/message')) return { time: {idle: 6, busy: 2} };
    if (!admitted) return [];
    return [
      {id: 'final', type: 'assistant', time: {created: 5}, content: [
        {type: 'text', text: 'Den Switch is off.'},
        {type: 'text', text: 'It is in Office.'},
      ]},
      {id: 'lookup', type: 'assistant', time: {created: 4}, content: [
        {type: 'text', text: 'Let me check what lights are available.'},
        {type: 'tool', name: 'status'},
      ]},
      {id: 'user', type: 'user', time: {created: 3}},
    ];
  };
  let progress;
  assert.equal(await runText('session', 'is my den light on', {api, onProgress: async rows => {progress = rows;}}),
    'Den Switch is off.\n\nIt is in Office.');
  assert(progress.some(row => row.id === 'lookup'));
});

import { steerText } from './opencode.mjs';
test('mid-generation input uses native steer delivery with exact text', async () => {
  const calls = [];
  await steerText('session', 'Only Shobha, please.', {api: async (...args) => calls.push(args)});
  assert.deepEqual(calls, [['/api/session/session/prompt', 'POST', {text: 'Only Shobha, please.', delivery: 'steer'}]]);
});

test('completion waits for steering admission and returns the revised final response once', async () => {
  let submitted = false, steered = false, finishChecks = 0;
  const posts = [];
  const user = {id: 'user', type: 'user', time: {created: 2}};
  const followup = {id: 'followup', type: 'user', time: {created: 5}};
  const answer = (id, created, text) => ({id, type: 'assistant', time: {created}, content: [{type: 'text', text}]});
  const api = async (path, method, body) => {
    if (method === 'POST') { posts.push(body); submitted = true; return; }
    if (path.endsWith('/permission')) return [];
    if (path.endsWith('/message')) return !submitted ? [] : steered
      ? [answer('revised', 6, 'Shobha only.'), followup, answer('old', 3, 'All three.'), user]
      : [answer('old', 3, 'All three.'), user];
    return {time: {idle: steered ? 7 : 4, busy: 2}};
  };
  assert.equal(await runText('session', 'All three', {api,
    onAdmitted: () => assert(submitted),
    onBeforeFinish: async () => {finishChecks++; if (!steered) {steered = true; return true;} return false;},
  }), 'Shobha only.');
  assert.equal(posts.length, 1);
  assert.equal(finishChecks, 2);
});

import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
test('voice progress and answer reply to the completed transcription', () => {
  const result = spawnSync(process.execPath, [fileURLToPath(new URL('./voice-routing.fixture.mjs', import.meta.url))], {encoding: 'utf8', timeout: 10000});
  assert.equal(result.status, 0, result.stderr || result.error?.message);
  assert.match(result.stdout, /Voice transcript, progress and final reply routing verified/);
});

for (const [command, failure] of [['/approve', false], ['/deny', false], ['/approve', true]]) {
  test(`permission handler submits ${command}${failure ? ' and reports API failure' : ''}`, () => {
    const result = spawnSync(process.execPath, [fileURLToPath(new URL('./permission-routing.fixture.mjs', import.meta.url)), command, ...(failure ? ['fail'] : [])], {encoding: 'utf8', timeout: 10000});
    assert.equal(result.status, 0, result.stderr || result.error?.message);
    assert.match(result.stdout, /Permission handler verified/);
  });
}

for (const scenario of ['stale', 'unbound', 'batch']) {
  test(`approval prompt ${scenario} cannot authorize a different or unreviewed pending request`, () => {
    const result = spawnSync(process.execPath, [fileURLToPath(new URL('./permission-routing.fixture.mjs', import.meta.url)), '/approve', scenario], {encoding: 'utf8', timeout: 10000});
    assert.equal(result.status, 0, result.stderr || result.error?.message);
    assert.match(result.stdout, /Permission handler verified/);
  });
}
