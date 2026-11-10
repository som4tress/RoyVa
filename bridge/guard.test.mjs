import test from 'node:test';
import assert from 'node:assert/strict';
import { loopVerdict, HARD_ROUNDS } from './guard.mjs';

const call = (name, input, status = 'completed') => ({type: 'tool', name, state: {input, status}});
const round = (...parts) => ({type: 'assistant', content: parts});

test('a long job made of different calls is not stopped (seven areas one by one)', () => {
  const rows = ['Dining Room', 'Hallway', 'Kitchen', 'Living Room', 'Office', 'Sitting Room', 'Stairs'].map(a => round(call('GetLiveContext', {area: a})));
  assert.equal(loopVerdict(rows), null);
});

test('the same call repeated is a loop', () => {
  const rows = [1, 2, 3].map(() => round(call('GetLiveContext', {area: 'Kitchen'})));
  assert.match(loopVerdict(rows), /same call/);
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
