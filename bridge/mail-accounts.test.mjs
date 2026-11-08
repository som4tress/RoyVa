import test from 'node:test';
import assert from 'node:assert/strict';
import {approvalKey, canonTool, mailAccount} from './permissions.mjs';

test('per-person Gmail server names map to the canonical tool names', () => {
  assert.equal(canonTool('gmail-u-dummy_modify_message'), 'gmail_modify_message');
  assert.equal(canonTool('gmail-tidy-u-dummy_tidy_matching'), 'gmail-tidy_tidy_matching');
  assert.equal(canonTool('gmail-tidy_tidy_matching'), 'gmail-tidy_tidy_matching');
  assert.equal(canonTool('home-assistant_x'), 'home-assistant_x');
  assert.equal(mailAccount('gmail-u-dummy_search_messages'), 'dummy');
  assert.equal(mailAccount('gmail_search_messages'), 'default');
});

test('a batch approval is never shared between mailboxes', () => {
  const p = (action) => ({action, metadata: {input: {action: 'trash'}}});
  assert.equal(approvalKey(p('gmail-tidy_tidy_matching')), 'gmail-tidy:trash');
  assert.equal(approvalKey(p('gmail-tidy-u-dummy_tidy_matching')), 'gmail-tidy:dummy:trash');
  assert.notEqual(approvalKey(p('gmail-tidy-u-a_tidy_matching')), approvalKey(p('gmail-tidy-u-b_tidy_matching')));
});
