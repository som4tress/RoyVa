import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { candidateFromSuccess } from '../src/plugins/ha-mcp-routing/learning.js';
import { rememberPhrase, findPhrase, phraseKindForTool } from '../src/plugins/ha-mcp-routing/phrases.js';

const dir = mkdtempSync(join(tmpdir(), 'learning-safety-'));
let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log('ok - ' + name); };

const child = (calls) => [{
  type: 'assistant', model: { providerID: 'evo-agent' },
  content: calls.map(c => ({ type: 'tool', name: c.name, state: { status: 'completed', input: c.input, output: '{}' } })),
}];

test('a verified history investigation is not learned as a single-tool route', () => {
  const candidate = candidateFromSuccess({
    text: 'How many motion-triggered recordings were there yesterday, along with their times?',
    task: 'Count recordings for yesterday',
    child: child([{ name: 'ha-event-history_get_entity_history', input: { name: 'front doorbell', date: '2026-10-31' } }]),
  });
  assert.equal(candidate, null, 'history investigations belong in procedure/correction stores, not routing shortcuts');
});

test('a verified device read still produces a route without a hardcoded target', () => {
  const candidate = candidateFromSuccess({
    text: 'What is the status of the den switch?',
    task: 'Read den switch status',
    child: child([{ name: 'ha-history_get_device_status', input: { name: 'Den Switch', domain: ['switch'] } }]),
  });
  assert.ok(candidate);
  assert.equal(candidate.target, undefined, 'no device may be hardcoded as a learned default');
  assert.equal(candidate.requiredTool, 'ha-history_get_device_status');
  assert.ok(candidate.anchors.includes('den') || candidate.anchors.includes('switch'));
});

test('media retrieval wording is never taught as a device route', () => {
  for (const text of ['send me the video clip', 'share the footage from last night']) {
    assert.equal(candidateFromSuccess({
      text,
      task: text,
      child: child([{ name: 'ha-history_get_device_status', input: { name: 'Front Doorbell' } }]),
    }), null);
  }
});

const phrasePath = join(dir, 'phrases.json');

test('the same wording cannot be taught as two different kinds', () => {
  assert.equal(rememberPhrase(phrasePath, 'how many doorbell events yesterday along with times', 'history', []), true);
  assert.equal(rememberPhrase(phrasePath, 'how many doorbell events yesterday along with times', 'devices', []), true);
  const stored = JSON.parse(readFileSync(phrasePath, 'utf8'));
  assert.ok(stored.phrases.every(p => p.ambiguous === true), JSON.stringify(stored.phrases));
  assert.equal(findPhrase(phrasePath, 'how many doorbell events yesterday along with times'), null);
});

test('a single consistent kind is still retrievable', () => {
  const path = join(dir, 'single.json');
  rememberPhrase(path, 'What is status of temple', 'devices', [{ name: 'Temple Light' }]);
  const hit = findPhrase(path, 'What is status of temple');
  assert.ok(hit);
  assert.equal(hit.kind, 'devices');
});

test('history-investigation tools never create a phrase-level route', () => {
  assert.equal(phraseKindForTool('ha-event-history_get_entity_history', { isError: false }), null);
  assert.equal(phraseKindForTool('ha-event-history_find_history_sources', { isError: false }), null);
  assert.equal(phraseKindForTool('ha-history_get_visited_locations', { isError: false }), 'history');
  assert.equal(phraseKindForTool('ha-history_get_device_status', { isError: false }), 'devices');
  assert.equal(phraseKindForTool('ha-event-history_get_entity_history', { isError: true }), null);
});

rmSync(dir, { recursive: true, force: true });
console.log(`\n${passed} learning-safety tests passed`);
