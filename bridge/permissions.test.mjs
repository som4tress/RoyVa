import test from 'node:test';
import assert from 'node:assert/strict';
import { BatchApprovals, approvalKey, formatPermission } from './permissions.mjs';

const perm = (action, input) => ({ id: 'p1', action, metadata: { input } });

test('only the bulk-tidy tools get a batch key, per action', () => {
  assert.equal(approvalKey(perm('gmail-tidy_tidy_matching', { action: 'trash', query: 'from:a.com' })), 'gmail-tidy:trash');
  assert.equal(approvalKey(perm('gmail-tidy_tidy_ids', { action: 'trash', ids: [] })), 'gmail-tidy:trash');
  assert.equal(approvalKey(perm('gmail-tidy_tidy_matching', { action: 'archive' })), 'gmail-tidy:archive');
  assert.equal(approvalKey(perm('gmail_send_message', {})), null);
  assert.equal(approvalKey(perm('ha-speakers_speak', {})), null);
});

test('one approval covers later batches of the same action only, in the same session only', () => {
  const b = new BatchApprovals();
  assert.equal(b.take('s1', 'gmail-tidy:trash'), false);          // nothing approved yet: ask
  b.grant('s1', 'gmail-tidy:trash');
  assert.equal(b.take('s1', 'gmail-tidy:trash'), true);
  assert.equal(b.take('s1', 'gmail-tidy:archive'), false);         // a different action still asks
  assert.equal(b.take('s2', 'gmail-tidy:trash'), false);           // another conversation still asks
  b.clear('s1');
  assert.equal(b.take('s1', 'gmail-tidy:trash'), false);           // approval ends with the run
});

test('auto-approval is capped', () => {
  const b = new BatchApprovals(2); b.grant('s', 'k');
  assert.deepEqual([b.take('s', 'k'), b.take('s', 'k'), b.take('s', 'k')], [true, true, false]);
});

test('the prompt says what will happen and that one approval covers the request', () => {
  const q = formatPermission(perm('gmail-tidy_tidy_matching', { action: 'trash', query: '{from:paypal.com from:nextdoor.com}' }));
  assert.match(q, /Move to Trash: every email matching: \{from:paypal.com from:nextdoor.com\}/); assert.match(q, /One \/approve covers this whole request/); assert.match(q, /30 days/);
  const ids = formatPermission(perm('gmail-tidy_tidy_ids', { action: 'archive', ids: ['a1b2c3d4', 'a1b2c3d5'] }));
  assert.match(ids, /Archive: 2 listed emails/);
});
