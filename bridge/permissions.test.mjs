import test from 'node:test';
import assert from 'node:assert/strict';
import { withoutOwnerDoors, BatchApprovals, approvalKey, formatPermission, idsInArgs, permissionVerified } from './permissions.mjs';

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
  assert.match(long, /could not be attached/);              // a long call that was not attached can never be approved from its card
  assert.doesNotMatch(long, /x{100}/);                      // and is never shown truncated
});

const writeCall = params => ({action: 'ha-api_ha_write', metadata: {input: {kind: 'ws', type: 'config/device_registry/update', params}}});
const live = {device_id: {dev1: {name: 'HAP-603WF-Bedroom'}}, area_id: {master_bedroom: {name: 'Master Bedroom'}}, floor_id: {}, entity_id: {}};

test('ha_write approval shows Home Assistant\'s own name next to each id', () => {
  const out = formatPermission(writeCall({device_id: 'dev1', area_id: 'master_bedroom'}), [], live);
  assert.match(out, /Device: HAP-603WF-Bedroom {2}\[dev1\]/);
  assert.match(out, /Area: Master Bedroom {2}\[master_bedroom\]/);
  assert.match(out, /\/approve or \/deny/);
  assert.equal(permissionVerified(writeCall({device_id: 'dev1'}), live), true);
});

test('an id Home Assistant does not know, or a failed lookup, makes the request unverified and approve is disabled', () => {
  const bad = formatPermission(writeCall({device_id: 'zzz'}), [], live);
  assert.match(bad, /Device zzz does not exist in Home Assistant/);
  assert.match(bad, /Approve is disabled/);
  assert.equal(permissionVerified(writeCall({device_id: 'zzz'}), live), false);
  const down = formatPermission(writeCall({device_id: 'dev1'}), [], null);
  assert.match(down, /unverified/);
  assert.equal(permissionVerified(writeCall({device_id: 'dev1'}), null), false);
});

test('calls without ids (an automation body, a command) need no lookup', () => {
  assert.deepEqual(idsInArgs({params: {alias: 'x', trigger: []}}), {device_id: [], entity_id: [], area_id: [], floor_id: []});
  assert.equal(permissionVerified({action: 'ha-api_ha_write', metadata: {input: {params: {alias: 'x'}}}}, undefined), true);
  assert.equal(permissionVerified({action: 'machine_run_approved', metadata: {input: {command: 'ls'}}}, undefined), true);
  assert.equal(permissionVerified({action: 'gmail_send_message', metadata: {input: {}}}, null), true);
});

test('ids inside nested service calls are all collected', () => {
  const ids = idsInArgs({params: {target: {entity_id: ['light.a', 'light.b'], area_id: 'kitchen'}}});
  assert.deepEqual(ids.entity_id, ['light.a', 'light.b']);
  assert.deepEqual(ids.area_id, ['kitchen']);
});

test('the remote takeover config never contains the owner-only doors', () => {
  const cfg = {mcp: {servers: {'home-assistant': {}, machine: {}, 'ha-api': {}, gmail: {}}}, other: 1};
  const out = withoutOwnerDoors(cfg);
  assert.deepEqual(Object.keys(out.mcp.servers), ['home-assistant', 'gmail']);
  assert.equal(out.other, 1);
  assert.ok(cfg.mcp.servers.machine);                         // the live config object is untouched
  assert.doesNotThrow(() => withoutOwnerDoors({}));
});

// ---- big approval calls: attached as a file, never refused for size, approval tied to the exact call
import {fullCallFile, callHash, editBlocked} from './permissions.mjs';
const bigWrite = text => ({id: 'p1', action: 'ha-api_ha_write', metadata: {input: {kind: 'rest', method: 'POST', path: '/api/config/automation/config/1', params: {alias: 'A', variables: {decision: text}}}}});

test('a long ha_write is attached as a file (with the full content), a short one is not', () => {
  const file = fullCallFile(bigWrite('x'.repeat(6000)));
  assert.ok(file && file.name.endsWith('.json') && file.content.includes('x'.repeat(6000)));
  assert.equal(fullCallFile(bigWrite('short')), null);
  assert.equal(fullCallFile({id: 'p', action: 'ha-turn_on', metadata: {input: {}}}), null);
});

test('the card for a long call says it is attached, shows the diff, and no longer says deny-and-split', () => {
  const card = formatPermission(bigWrite('x'.repeat(6000)), [], undefined, {attached: true, diff: ['+ variables.map_link: "…"', '~ variables.msg: \'a\' -> \'b\'']});
  assert.match(card, /attached above as a file/);
  assert.match(card, /Changes compared with what is saved now:\n\+ variables\.map_link/);
  assert.doesNotMatch(card, /Too long|smaller step/);
  assert.match(card, /\/approve or \/deny/);
  assert.ok(card.length < 900);                                  // fits one Telegram message however big the call is
});

test('if a long call could not be attached, approving is disabled', () => {
  const card = formatPermission(bigWrite('x'.repeat(6000)), [], undefined, {attached: false});
  assert.match(card, /could not be attached/);
  assert.match(card, /Approve is disabled/);
  assert.doesNotMatch(card, /\/approve or \/deny/);
});

test('"no difference" and "could not compare" are stated, not silently omitted', () => {
  assert.match(formatPermission(bigWrite('s'), [], undefined, {diff: []}), /No difference from what is saved now/);
  assert.match(formatPermission(bigWrite('s'), [], undefined, {diff: null}), /Could not compare/);
  assert.doesNotMatch(formatPermission(bigWrite('s'), [], undefined, {}), /compare|difference/);
});

test('the call fingerprint ignores key order and changes with any content change', () => {
  const a = {kind: 'rest', params: {x: 1, y: [1, 2]}};
  assert.equal(callHash(a), callHash({params: {y: [1, 2], x: 1}, kind: 'rest'}));
  assert.notEqual(callHash(a), callHash({kind: 'rest', params: {x: 1, y: [1, 3]}}));
});

// ---- ha_edit: the card shows the edits, the diff and how the added template renders; no good preview = no Approve
const editCall = {id: 'p9', action: 'ha-api_ha_edit', metadata: {input: {domain: 'automation', id: '17', version: 'abc', edits: [{op: 'append', path: 'variables.msg', text: ' x'}]}}};
const goodPreview = {ok: true, problem: null, edits: ['append variables.msg: x'], lines: ["~ variables.msg: …'Parked.' -> 'Parked. x'…"],
  renders: [{path: 'variables.msg', status: 'ok', rendered: 'https://maps?q=1,2'}]};

test('an edit card lists the edits, the diff and the rendered text, and offers Approve', () => {
  const text = formatPermission(editCall, [], undefined, {preview: goodPreview});
  assert.match(text, /Edit a saved Home Assistant automation: 17/);
  assert.match(text, /append variables\.msg/);
  assert.match(text, /Changes compared with what is saved now/);
  assert.match(text, /Renders now at variables\.msg: https:\/\/maps\?q=1,2/);
  assert.match(text, /\/approve or \/deny \(this edit only\)/);
  assert.equal(editBlocked({preview: goodPreview}), false);
});

test('an edit with a failing template, a stale version, or no preview cannot be approved', () => {
  const failing = {...goodPreview, ok: false, problem: 'the template added at variables.msg does not render: from_json', renders: [{path: 'variables.msg', status: 'error', error: 'from_json got invalid input'}]};
  const text = formatPermission(editCall, [], undefined, {preview: failing});
  assert.match(text, /fails: from_json/);
  assert.match(text, /Approve is disabled/);
  assert.equal(editBlocked({preview: failing}), true);
  const none = formatPermission(editCall, [], undefined, {preview: null});
  assert.match(none, /Could not build a preview/);
  assert.match(none, /Approve is disabled/);
  assert.equal(editBlocked({preview: null}), true);
  assert.equal(editBlocked({}), true);
});

test('template text that needs the automation\'s own variables is reported, not blamed', () => {
  const ctx = {...goodPreview, renders: [{path: 'variables.msg', status: 'needs_context'}]};
  const text = formatPermission(editCall, [], undefined, {preview: ctx});
  assert.match(text, /could not be tested alone/);
  assert.match(text, /\/approve or \/deny/);
});

test('a blank render is shown as a warning on the edit card but does not disable Approve', () => {
  const blank = {...goodPreview, renders: [{path: 'variables.msg', status: 'empty', rendered: ''}]};
  const text = formatPermission(editCall, [], undefined, {preview: blank});
  assert.match(text, /renders to NOTHING/);
  assert.match(text, /\/approve or \/deny/);
  assert.equal(editBlocked({preview: blank}), false);
});

test('placeholders and link warnings appear on the edit card', () => {
  const pv = {...goodPreview, warnings: ['a link in the text added at variables.msg is followed by a punctuation character'],
    renders: [{path: 'variables.msg', status: 'ok', rendered: 'In PARK.\nhttps://maps?q=1,2.', placeholders: ['decision', 'current']}]};
  const text = formatPermission(editCall, [], undefined, {preview: pv});
  assert.match(text, /with empty placeholders for decision, current/);
  assert.match(text, /followed by a punctuation character/);
  assert.match(text, /\/approve or \/deny/);
});
