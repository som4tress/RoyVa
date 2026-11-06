import {test, mock} from 'node:test';
import assert from 'node:assert/strict';
let calls = [], clientCalls = 0, fail = false;
const gmail = {users: {messages: {batchModify: async request => {calls.push(request); if (fail) throw Error('fixture failure'); return {data: {}};}}}};
mock.module(new URL('../dist/oauth.js', import.meta.url).href, {namedExports: {getGmailClient: async () => {clientCalls++; return gmail;}}});
const {batchModifyMessages} = await import('../dist/tools.js');
test('one call applies only the explicit batch IDs and label changes', async () => {
  calls = []; clientCalls = 0;
  const input = {messageIds: ['one', 'two'], addLabelIds: ['TRASH'], removeLabelIds: ['INBOX']};
  const result = await batchModifyMessages(input);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], {userId: 'me', requestBody: {ids: ['one', 'two'], addLabelIds: ['TRASH'], removeLabelIds: ['INBOX']}});
  assert.equal(result.submitted_count, 2);
  assert.match(result.status, /not separately verified/);
  assert.deepEqual(input.messageIds, ['one', 'two']);
});
test('invalid, empty, duplicate, excessive and implicit targets never reach Gmail', async () => {
  calls = []; clientCalls = 0;
  for (const ids of [[], ['same', 'same'], ['*'], ['all'], ['from:uber'], [' '], Array.from({length: 1001}, (_, i) => String(i))]) {
    await assert.rejects(batchModifyMessages({messageIds: ids, addLabelIds: ['TRASH']}));
  }
  assert.equal(clientCalls, 0);
  assert.equal(calls.length, 0);
});
test('missing, malformed and conflicting label changes never reach Gmail', async () => {
  calls = []; clientCalls = 0;
  for (const changes of [{}, {addLabelIds: 'TRASH'}, {addLabelIds: ['']}, {addLabelIds: ['TRASH'], removeLabelIds: ['TRASH']}]) {
    await assert.rejects(batchModifyMessages({messageIds: ['one'], ...changes}));
  }
  assert.equal(clientCalls, 0);
  assert.equal(calls.length, 0);
});
test('Gmail failure is propagated without retries or a false success count', async () => {
  calls = []; fail = true;
  await assert.rejects(batchModifyMessages({messageIds: ['one'], addLabelIds: ['TRASH']}), /fixture failure/);
  assert.equal(calls.length, 1);
  fail = false;
});
