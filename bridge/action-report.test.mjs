import test from 'node:test';
import assert from 'node:assert/strict';
import { actionReport } from './bridge.mjs';

const writes = { 'ha-speakers_speak': 'Speak text aloud on speakers (text-to-speech)', 'ha-routines_run_routine': 'Run an existing routine' };
const routed = { can_act: true, write_tools: writes };
const tool = (name, status, payload) => ({ type: 'tool', name, state: { status, content: [{ type: 'text', text: JSON.stringify(payload) }] } });
const rows = parts => [{ type: 'assistant', content: parts }];

test('reports each completed write with the tool\'s own plain-language line', () => {
  const out = actionReport(rows([tool('ha-routines_run_routine', 'completed', { ok: true, did: "Ran routine 'Good Night' (automation.trigger)" })]), routed);
  assert.match(out, /What I did/); assert.match(out, /✅ Ran routine 'Good Night'/);
});
test('a dry run says so (it is in the tool\'s own line)', () => {
  const out = actionReport(rows([tool('ha-speakers_speak', 'completed', { ok: true, did: '[DRY RUN, nothing happened] Spoke 12 characters on Kitchen' })]), routed);
  assert.match(out, /DRY RUN, nothing happened/);
});
test('a tool that returned ok:false or errored is reported as failed, never as done', () => {
  assert.match(actionReport(rows([tool('ha-speakers_speak', 'completed', { ok: false, error: "no speaker matches 'garage'" })]), routed), /❌ .*no speaker matches 'garage'/);
  assert.match(actionReport(rows([tool('ha-routines_run_routine', 'error', {})]), routed), /❌ Run an existing routine: error/);
});
test('says plainly when the turn could act but nothing ran (a model cannot claim an action it did not take)', () => {
  assert.match(actionReport(rows([{ type: 'text', text: 'Done! I played it.' }]), routed), /No action was taken/);
});
test('read-only tools never appear and a turn that cannot act adds nothing', () => {
  assert.equal(actionReport(rows([tool('ha-speakers_list_speakers', 'completed', { speakers: [] })]), { can_act: false, write_tools: {} }), '');
  assert.match(actionReport(rows([tool('ha-speakers_list_speakers', 'completed', { speakers: [] })]), routed), /No action was taken/);
});
test('handles result content given as a JSON string instead of an array, and several actions in order', () => {
  const p1 = { type: 'tool', name: 'ha-speakers_speak', state: { status: 'completed', content: JSON.stringify([{ type: 'text', text: JSON.stringify({ ok: true, did: 'Spoke on A' }) }]) } };
  const out = actionReport(rows([p1, tool('ha-routines_run_routine', 'completed', { ok: true, did: 'Ran B' })]), routed);
  assert.ok(out.indexOf('Spoke on A') < out.indexOf('Ran B'));
});
