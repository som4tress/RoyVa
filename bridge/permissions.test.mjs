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
  assert.match(q, /Move to Trash: every email matching: \{from:paypal.com from:nextdoor.com\}/); assert.match(q, /covers the whole request/); assert.ok(q.split('\n').length === 3);
  const ids = formatPermission(perm('gmail-tidy_tidy_ids', { action: 'archive', ids: ['a1b2c3d4', 'a1b2c3d5'] }));
  assert.match(ids, /Archive: 2 listed emails/);
});

test('generic approval prompts are short: no JSON dump, no tool-id boilerplate', () => {
  const out = formatPermission(perm('ha-routines_run_routine', { name: 'Good Night', extra: 'x'.repeat(2000) }));
  assert.ok(out.split('\n').length <= 5 && out.length < 400, out);
  assert.match(out, /^Approve\?/); assert.match(out, /\/approve or \/deny/);
  assert.doesNotMatch(out, /Exact arguments|Permission resources|Tool:/);
});

test('sending email shows the recipient and subject, briefly', () => {
  const out = formatPermission(perm('gmail_send_message', { to: 'a@b.com', subject: 'Hi', body: 'long '.repeat(500) }));
  assert.match(out, /Send email/); assert.match(out, /To: a@b.com/); assert.match(out, /Text: long long/); assert.ok(out.length < 400);
});

test('arbitrary-power tools show the whole call and are never batch-approved', () => {
  const p = a => ({action: a, metadata: {input: {host: 'h', command: "echo 'a;b'\nrm x"}}});
  const out = formatPermission(p('machine_remote_run_approved'));
  assert.match(out, /REMOTE machine/);
  assert.match(out, /echo 'a;b'\\nrm x/);                 // newline shown escaped
  assert.match(out, /this call only/);
  assert.equal(approvalKey(p('machine_run_approved')), null);
  const long = formatPermission({action: 'ha-api_ha_write', metadata: {input: {params: 'x'.repeat(5000)}}});
  assert.match(long, /Too long to review/);
});

const haRead = (type, data) => ({type: 'assistant', content: [{type: 'tool', name: 'ha-api_ha_read', state: {input: {kind: 'ws', type}, content: [{type: 'text', text: JSON.stringify(data)}]}}]});
const writeCall = params => ({action: 'ha-api_ha_write', metadata: {input: {kind: 'ws', type: 'config/device_registry/update', params}}});

test('ha_write approval names the device and area from the matching registries', () => {
  const rows = [haRead('config/device_registry/list', {result: {matched: 1, items: [{id: 'dev1', name: 'HAP-603WF-Bedroom', name_by_user: null, area_id: 'master_bedroom'}]}}),
                haRead('config/area_registry/list', {result: [{area_id: 'master_bedroom', name: 'Master Bedroom'}]})];
  const out = formatPermission(writeCall({device_id: 'dev1', area_id: 'master_bedroom'}), rows);
  assert.match(out, /Device: HAP-603WF-Bedroom/);
  assert.match(out, /Area: Master Bedroom/);
  assert.doesNotMatch(out, /Area: HAP/);                           // a device that sits in the area must not name the area
});

test('an id is never named from another registry or from a display name the user cannot trust', () => {
  const rows = [haRead('config/entity_registry/list', {result: [{entity_id: 'switch.x', device_id: 'dev1', name: 'Some Entity Name'}]}),
                haRead('config/device_registry/list', {result: [{id: 'dev1', name: 'Real Device', name_by_user: 'My Renamed Device'}]})];
  const out = formatPermission(writeCall({device_id: 'dev1'}), rows);
  assert.match(out, /Device: My Renamed Device/);                  // the UI name wins, and the entity that points at this device does not rename it
  assert.doesNotMatch(out, /Some Entity Name/);
  assert.match(formatPermission(writeCall({device_id: 'dev1'}), [rows[0]]), /Device: name not found/);   // only an entity read: the device stays unnamed
  assert.match(formatPermission(writeCall({device_id: 'zzz'}), rows), /name not found in this conversation/);
});

test('entity names come from states reads', () => {
  const rows = [{type: 'assistant', content: [{type: 'tool', name: 'ha-api_ha_read', state: {input: {kind: 'rest', path: '/api/states'}, content: [{type: 'text', text: JSON.stringify({http_status: 200, body: {items: [{entity_id: 'light.kitchen', attributes: {friendly_name: 'Kitchen Light'}}]}})}]}}]}];
  assert.match(formatPermission({action: 'ha-api_ha_write', metadata: {input: {kind: 'rest', path: '/api/services/light/turn_off', params: {entity_id: 'light.kitchen'}}}}, rows), /Entity: Kitchen Light/);
});
