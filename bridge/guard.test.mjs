import test from 'node:test';
import assert from 'node:assert/strict';
import { loopVerdict, HARD_ROUNDS } from './guard.mjs';

const call = (name, input, status = 'completed') => ({type: 'tool', name, state: {input, status}});
const round = (...parts) => ({type: 'assistant', content: parts});

test('a long job made of different calls is not stopped (seven areas one by one)', () => {
  const rows = ['Dining Room', 'Hallway', 'Kitchen', 'Living Room', 'Office', 'Sitting Room', 'Stairs'].map(a => round(call('GetLiveContext', {area: a})));
  assert.equal(loopVerdict(rows), null);
});

test('the same call repeated in separate rounds after finishing is a loop', () => {
  const rows = [1, 2, 3].map(() => round(call('GetLiveContext', {area: 'Kitchen'})));
  assert.match(loopVerdict(rows), /same call/);
});

test('identical calls fired together in one round, or still running, are not a loop', () => {
  const running = status => ({type: 'tool', name: 'ha-history_get_device_status_report', state: {input: {}, status}});
  assert.equal(loopVerdict([round(running('running'), running('running'), running('running'))]), null);       // the real case: three at once, none finished
  assert.equal(loopVerdict([round(running('completed'), running('completed'), running('completed'))]), null);  // all together in one round
  assert.equal(loopVerdict([round(running('completed')), round(running('completed')), round(running('running'))]), null);   // two finished, third still running
});

test('failed calls in a row are a loop; an interrupted call is not a repeat or a failure of the run', () => {
  const failing = [1, 2, 3, 4].map(n => round(call('machine_run', {command: `x${n}`}, 'error')));
  assert.match(loopVerdict(failing), /failed calls in a row/);
  const aborted = [1, 2, 3].map(() => round({type: 'tool', name: 'GetLiveContext', state: {input: {}, status: 'error', error: {type: 'aborted'}}}));
  assert.equal(loopVerdict(aborted), null);
});

test('the hard ceiling still applies', () => {
  const rows = Array.from({length: HARD_ROUNDS + 1}, (_, n) => round(call('t', {n})));
  assert.match(loopVerdict(rows), /rounds/);
});

// ---- approval-gated tools: a refusal means "blocked", not "try another route" (the 2026-11-13 Ford edit burned 28 rounds this way)
const result = (name, text, input = {}) => ({type: 'tool', name, state: {input, status: 'completed', content: [{type: 'text', text}]}});
const refusal = name => result(name, JSON.stringify({error: 'that command reads or uses credentials'}), {n: Math.random()});

test('two refused gated calls in a row stop the run, even with reads in between', () => {
  const rows = [round(refusal('ha-api_ha_write')), round(call('ha-api_ha_read', {path: '/api/states'})), round(refusal('machine_run_approved'))];
  assert.match(loopVerdict(rows), /refused calls in a row/);
});

test('one refusal followed by a call that works is fine, and Home Assistant errors are not refusals', () => {
  const ok = result('ha-api_ha_write', JSON.stringify({done: {}, http_status: 200}), {a: 1});
  assert.equal(loopVerdict([round(refusal('ha-api_ha_write')), round(ok)]), null);
  const haError = n => result('ha-api_ha_write', JSON.stringify({done: {}, http_status: 400, body: 'bad'}), {n});
  assert.equal(loopVerdict([round(haError(1)), round(haError(2)), round(haError(3))]), null);
});

test('refusals from tools that are not approval-gated do not count', () => {
  const r = n => result('ha-history_get_visited_locations', JSON.stringify({error: 'person must be one of'}), {n});
  assert.equal(loopVerdict([round(r(1)), round(r(2)), round(r(3))]), null);
});

// ---- lost: four lookups in a row that find nothing (the 2026-11-14 Ford retest went on to `find /` and `grep -r`)
test('four lookups in a row that found nothing stop the run; data in between resets the count', () => {
  const miss = n => round(result('ha-api_ha_read', JSON.stringify({http_status: 404, body: '404: Not Found'}), {n}));
  const hit = n => round(result('ha-api_ha_read', JSON.stringify({http_status: 200, body: [{id: 'x'}]}), {n}));
  assert.match(loopVerdict([miss(1), miss(2), miss(3), miss(4)]), /found nothing/);
  assert.equal(loopVerdict([miss(1), miss(2), miss(3), hit(4), miss(5), miss(6), miss(7)]), null);
});

test('the kinds of "nothing found": no match, unknown command, empty list, empty command output', () => {
  const rows = [
    round(result('ha-api_ha_read', JSON.stringify({error: "no automation matches 'x'", all_names: ['a']}), {n: 1})),
    round(result('ha-routines_list_routines', JSON.stringify({routines: []}), {n: 2})),
    round({type: 'tool', name: 'ha-api_ha_read', state: {input: {n: 3}, status: 'error', error: {type: 'tool.execution', message: 'unknown_command'}}}),
    round(result('machine_run', JSON.stringify({exit_code: 0, stdout: '', stderr: '', sandbox: true}), {n: 4}))];
  assert.match(loopVerdict(rows), /found nothing/);
});

test('a normal reply with data, or a still-running call, is never a miss', () => {
  const ok = n => round(result('t', JSON.stringify({exit_code: 0, stdout: 'hello'}), {n}));
  assert.equal(loopVerdict([1, 2, 3, 4, 5].map(ok)), null);
  const running = round({type: 'tool', name: 't', state: {input: {}, status: 'running'}});
  assert.equal(loopVerdict([running, running, running, running]), null);
});
