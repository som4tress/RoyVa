import assert from 'node:assert/strict';
import {
  parseHistoryRequest, isPersonLocationHistory, isEntityHistory,
  resolveHistoryScope, scopePreserved, resolveWindow, localDay, shiftLocalDay,
} from '../src/lib/history-scope.mjs';

const NOW = Date.parse('2026-11-01T18:00:00Z'); // 2026-11-01 11:00 America/Los_Angeles
let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log('ok - ' + name); };

test('local day and yesterday are timezone-correct', () => {
  assert.equal(localDay(NOW, 'America/Los_Angeles'), '2026-11-01');
  assert.equal(shiftLocalDay('2026-11-01', -1), '2026-10-31');
  assert.equal(shiftLocalDay('2026-03-01', -1), '2026-02-28');
  assert.equal(shiftLocalDay('2026-01-01', -1), '2025-12-31');
  const window = resolveWindow('yesterday', { now: NOW, timeZone: 'America/Los_Angeles' });
  assert.equal(window.kind, 'local_day');
  assert.equal(window.date, '2026-10-31');
  assert.equal(window.from, '2026-10-31T00:00:00');
  assert.equal(window.to, '2026-11-01T00:00:00');
});

test('recording question parses motion scope, window and times request', () => {
  const plan = parseHistoryRequest('How many motion-triggered Ring recordings were there yesterday, along with their times?', { now: NOW });
  assert.ok(plan);
  assert.equal(plan.kind, 'entity_history');
  assert.equal(plan.requiresGeneralTools, true);
  assert.equal(plan.window.date, '2026-10-31');
  assert.deepEqual(plan.eventKinds, ['motion'], 'the object noun "recordings" must not become the trigger type');
  assert.equal(plan.asksForCount, true);
  assert.equal(plan.asksForTimes, true);
  assert.ok(plan.selectorTokens.includes('ring'));
});

test('singular doorbell request keeps singular plurality', () => {
  const plan = parseHistoryRequest('Show me the front doorbell motion recordings from yesterday', { now: NOW });
  assert.ok(plan);
  assert.equal(plan.plurality, 'singular');
  assert.deepEqual(plan.eventKinds, ['motion']);
  assert.ok(plan.selectorTokens.includes('doorbell'));
  assert.ok(plan.selectorTokens.includes('front'));
  assert.ok(!plan.selectorTokens.includes('yesterday'));
});

test('all/every request is plural; explicit dates and rolling hours resolve', () => {
  assert.equal(parseHistoryRequest('Show recordings from every camera yesterday', { now: NOW }).plurality, 'plural');
  assert.equal(parseHistoryRequest('camera recordings on 2026-10-29', { now: NOW }).window.date, '2026-10-29');
  const rolling = parseHistoryRequest('doorbell events in the last 6 hours', { now: NOW });
  assert.equal(rolling.window.kind, 'rolling');
  assert.equal(rolling.window.hours, 6);
});

test('person visit history is never parsed as entity history', () => {
  for (const text of [
    'Where did Shobha go yesterday',
    'Show me the locations Shobha visited today',
    'Where has Shivangsh been this week',
  ]) {
    assert.equal(isPersonLocationHistory(text), true, 'expected person history: ' + text);
    assert.equal(isEntityHistory(text), false, 'must not be entity history: ' + text);
    assert.equal(parseHistoryRequest(text, { now: NOW }), null);
  }
});

test('camera/recording history is not person-location history', () => {
  for (const text of [
    'How many ring doorbell events yesterday, along with times',
    'Show me the history of the side camera motion yesterday',
  ]) {
    assert.equal(isPersonLocationHistory(text), false, text);
    assert.equal(isEntityHistory(text), true, text);
    assert.ok(parseHistoryRequest(text, { now: NOW }), text);
  }
});

test('unwindowed history request is parsed but flagged, not silently defaulted', () => {
  const plan = parseHistoryRequest('Show me the history of b-hyve watering', { now: NOW });
  assert.ok(plan);
  assert.equal(plan.window, null);
  assert.ok(plan.limitations.some(l => /window/i.test(l)));
});

test('future window is flagged', () => {
  const plan = parseHistoryRequest('camera events tomorrow', { now: NOW });
  assert.ok(plan);
  assert.equal(plan.window.future, true);
});

const catalog = [
  { entity_id: 'sensor.front_doorbell_last_activity', name: 'Front Doorbell Timestamp', domain: 'sensor', device_name: 'Front Doorbell' },
  { entity_id: 'sensor.front_driveway_last_activity', name: 'Front Driveway Timestamp', domain: 'sensor', device_name: 'Front Driveway' },
  { entity_id: 'sensor.backyard_last_activity', name: 'Backyard Timestamp', domain: 'sensor', device_name: 'Backyard' },
  { entity_id: 'camera.front_doorbell_live_view', name: 'Front Doorbell', domain: 'camera', device_name: 'Front Doorbell' },
  { entity_id: 'camera.front_driveway_live_view', name: 'Front Driveway', domain: 'camera', device_name: 'Front Driveway' },
];

test('singular device resolves to exactly one device with no scope errors', () => {
  const plan = parseHistoryRequest('Show me the front doorbell motion recordings from yesterday', { now: NOW });
  const resolution = resolveHistoryScope(plan, catalog);
  assert.equal(resolution.matched.length, 1);
  assert.equal(resolution.matched[0].entity_id, 'sensor.front_doorbell_last_activity');
  assert.deepEqual(scopePreserved(plan, resolution), []);
});

test('singular request matching two devices is refused, never merged', () => {
  const plan = parseHistoryRequest('Show me the front camera motion recordings from yesterday', { now: NOW });
  const resolution = resolveHistoryScope(plan, catalog);
  assert.equal(resolution.matched.length, 2);
  const errors = scopePreserved(plan, resolution);
  assert.ok(errors.includes('scope_broadened'), JSON.stringify(errors));
  assert.ok(errors.includes('mixed_entities_for_singular_request'));
});

test('plural brand scope may match several devices but must name them', () => {
  const plan = parseHistoryRequest('Show recordings from every camera yesterday', { now: NOW });
  // "every camera" has no brand words; a catalog containing only cameras resolves after tokens.
  const resolution = resolveHistoryScope({ ...plan, selectorTokens: ['front'] }, catalog);
  assert.ok(resolution.matched.length >= 1);
  assert.ok(!scopePreserved(plan, resolution).includes('scope_broadened'));
});

test('unmatched request reports unresolved, not absence', () => {
  const plan = parseHistoryRequest('Show me the front gate camera motion recordings yesterday', { now: NOW });
  const resolution = resolveHistoryScope(plan, catalog);
  assert.equal(resolution.matched.length, 0);
  const errors = scopePreserved(plan, resolution);
  assert.ok(errors.includes('no_resolved_entities'));
  assert.ok(resolution.problems.join(' ').includes('not proof'), resolution.problems.join(' '));
});

test('an explicit exclusion narrows the resolved set', () => {
  const plan = parseHistoryRequest('Show me the front camera motion recordings yesterday, not the driveway', { now: NOW });
  assert.ok(plan);
  assert.deepEqual(plan.excludedTokens, ['driveway']);
  const resolution = resolveHistoryScope(plan, catalog);
  assert.deepEqual(resolution.matched.map(m => m.entity_id), ['sensor.front_doorbell_last_activity']);
});

test('no device words asks for clarification', () => {
  const plan = parseHistoryRequest('How many motion recordings were there yesterday', { now: NOW });
  const resolution = resolveHistoryScope(plan, catalog);
  assert.ok(resolution.problems.join(' ').includes('unresolved_scope'));
});

console.log(`\n${passed} history-scope tests passed`);
