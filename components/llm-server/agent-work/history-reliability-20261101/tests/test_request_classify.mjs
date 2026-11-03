import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { classify, isMixedRequest } from '../src/lib/ha-request-classify.mjs';

let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log('ok - ' + name); };

test('complaint prompts route to a read-only investigation, not orchestration', () => {
  const prompts = [
    'How many motion-triggered Ring recordings were there yesterday, along with their times?',
    'How many ring doorbell events yesterday, along with times',
    'Show me the front doorbell motion recordings from yesterday',
    'How many times did the doorbell detect motion yesterday?',
    'In Home Assistant, how many Ring doorbell recordings yesterday?',
    'Show me the history of b-hyve watering',
    'Did b-hyve water today',
    'Show me the history of the side camera motion yesterday',
  ];
  for (const text of prompts) {
    assert.equal(isMixedRequest(text), false, 'must not be orchestrated: ' + text);
    assert.equal(classify(text), 'investigation', 'must be an investigation: ' + text);
  }
});

test('person visit history still classifies as history', () => {
  for (const text of [
    'Where did Shobha go yesterday',
    'Show me Shobha\'s location history in the last hour',
    'Where has Shivangsh been this week',
  ]) {
    assert.equal(classify(text), 'history', text);
  }
});

test('media retrieval stays a mixed task with an honest capability limitation', () => {
  for (const text of [
    'Send me the front doorbell clip from yesterday',
    'In Home Assistant, share the driveway video from last night',
  ]) {
    assert.equal(isMixedRequest(text), true, text);
    assert.equal(classify(text), null, text);
  }
});

test('ordinary controls and status reads are unchanged', () => {
  assert.equal(classify('turn on the kitchen light'), 'devices');
  assert.equal(classify('Turn off living room tv'), 'devices');
  assert.equal(classify('Is the kitchen dimmer on?'), 'devices');
  assert.equal(classify('What is status of temple'), null, 'a bare room label relies on learned phrases, as before');
});

test('coding, configuration and routing explanations are not hijacked by history parsing', () => {
  assert.equal(classify('write a script to count camera events yesterday'), null);
  assert.equal(classify('explain how openrouter routing chooses models'), null);
  assert.equal(classify('assign the driveway camera entities to the front yard area'), null);
});

test('routing modules contain no household device/room/brand literals', () => {
  // Household member names are identity data for presence, not device routing.
  const banned = /\b(kitchen|island|den switch|living room|media wall|sonos|bhyve|orbit|driveway|backyard|temple)\b/i;
  for (const file of [
    '../src/lib/history-scope.mjs',
    '../src/lib/history-routing.mjs',
    '../src/lib/history-contract.mjs',
    '../src/lib/ha-request-classify.mjs',
  ]) {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/(^|\s)\/\/[^\n]*/g, ' ');
    const hit = source.match(banned);
    assert.equal(hit, null, file + ' contains hardcoded ' + (hit && hit[0]));
  }
});

console.log(`\n${passed} request-classification tests passed`);
