import assert from 'node:assert/strict';
import { parseHistoryRequest, resolveHistoryScope } from '../src/lib/history-scope.mjs';
import {
  buildHistoryContract, validateHistoryClaim, renderHistoryAnswer,
  EVIDENCE, normalizeRows,
} from '../src/lib/history-contract.mjs';
import { decideHistoryRoute, answerScopeErrors } from '../src/lib/history-routing.mjs';

const NOW = Date.parse('2026-11-01T18:00:00Z');
const TZ = 'America/Los_Angeles';
let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log('ok - ' + name); };

const catalog = [
  { entity_id: 'sensor.front_doorbell_last_activity', name: 'Front Doorbell Timestamp', domain: 'sensor', device_name: 'Front Doorbell' },
  { entity_id: 'sensor.front_driveway_last_activity', name: 'Front Driveway Timestamp', domain: 'sensor', device_name: 'Front Driveway' },
];

const rows = [
  { entity_id: 'sensor.front_doorbell_last_activity', name: 'Front Doorbell Timestamp', created_at: '2026-10-31T16:46:00Z', state: 'motion', category: 'motion', recording_status: 'ready' },
  { entity_id: 'sensor.front_doorbell_last_activity', name: 'Front Doorbell Timestamp', created_at: '2026-10-31T16:47:07Z', state: 'motion', category: 'motion', recording_status: 'ready' },
  { entity_id: 'sensor.front_doorbell_last_activity', name: 'Front Doorbell Timestamp', created_at: '2026-10-31T18:33:39Z', state: 'motion', category: 'motion', recording_status: 'ready' },
];

const singularPlan = parseHistoryRequest('Show me the front doorbell motion recordings from yesterday', { now: NOW });
const singularResolution = resolveHistoryScope(singularPlan, catalog);
const singularContract = buildHistoryContract({
  plan: singularPlan,
  resolution: singularResolution,
  rows,
  source: 'Home Assistant recorder',
  evidenceClass: EVIDENCE.OBSERVED_METADATA,
  artifact: 'evidence/doorbell-2026-10-31.md',
  timeZone: TZ,
});

test('contract keeps requested window, scope and evidence class', () => {
  assert.equal(singularContract.total, 3);
  assert.equal(singularContract.requested.window.date, '2026-10-31');
  assert.equal(singularContract.resolution_placeholder, undefined);
  assert.equal(singularContract.resolved.entities.length, 1);
  assert.equal(singularContract.evidence_class, 'observed_metadata');
  assert.equal(singularContract.completeness.provider_complete, false);
  assert.equal(singularContract.counts_by_entity[0].count, 3);
  assert.equal(singularContract.rows[0].at_local, '2026-10-31 09:46:00');
});

test('quantitative claims carry filter semantics and a unique-key definition', () => {
  assert.ok(singularContract.filter_semantics);
  assert.equal(singularContract.filter_semantics.dedupe_key, 'created_at');
  assert.deepEqual(singularContract.filter_semantics.trigger_types, ['motion']);
  assert.ok(singularContract.unique_key_definition.includes('created_at'));
  const missing = validateHistoryClaim({ ...singularContract, unique_key_definition: undefined }, { total: 3, text: 'HA-observed 3', qualified: true });
  assert.ok(missing.errors.includes('unique_key_undefined'));
});

test('a claim of complete provider coverage is rejected for observed metadata', () => {
  const result = validateHistoryClaim(singularContract, { total: 3, text: 'HA-observed metadata: 3 motion events.', qualified: true, claims_complete_provider: true });
  assert.ok(result.errors.includes('false_completeness'));
});

test('a count that exceeds the returned rows is rejected', () => {
  const result = validateHistoryClaim(singularContract, { total: 35, text: 'HA-observed: 35 motion events', qualified: true });
  assert.equal(result.ok, false);
  assert.ok(result.errors.some(e => e.startsWith('count_mismatch')));
});

test('observed metadata cannot be presented as provider-authoritative', () => {
  const unlabelled = validateHistoryClaim(singularContract, { total: 3, text: '3 motion recordings from the doorbell.' });
  assert.ok(unlabelled.errors.some(e => e.startsWith('provenance_unstated')));
  const authoritative = validateHistoryClaim(singularContract, { total: 3, text: 'HA-observed: 3 motion events; this is the complete Ring list.', says_authoritative: true, qualified: true });
  assert.ok(authoritative.errors.some(e => e.startsWith('false_authority')));
  const good = validateHistoryClaim(singularContract, { total: 3, text: 'HA-observed metadata: 3 motion events for the doorbell on 2026-10-31.', qualified: true, window_stated: true });
  assert.equal(good.ok, true, JSON.stringify(good.errors));
});

test('merging an unrequested device is rejected', () => {
  const mixed = buildHistoryContract({
    plan: { ...singularPlan, plurality: 'unspecified' },
    resolution: { matched: catalog, problems: [] },
    rows: [...rows, { entity_id: 'sensor.front_driveway_last_activity', name: 'Front Driveway Timestamp', created_at: '2026-10-31T17:00:00Z', category: 'motion' }],
    evidenceClass: EVIDENCE.OBSERVED_METADATA,
  });
  const unnamed = validateHistoryClaim(mixed, { total: mixed.total, text: 'HA-observed: 4 motion events.', qualified: true });
  assert.ok(unnamed.errors.some(e => e.startsWith('mixed_devices_unstated')), JSON.stringify(unnamed.errors));

  const named = validateHistoryClaim(mixed, { total: mixed.total, text: 'HA-observed: 4 motion events across Front Doorbell Timestamp and Front Driveway Timestamp.', qualified: true });
  assert.equal(named.ok, true, JSON.stringify(named.errors));
});

test('per-device counts must sum to the total', () => {
  const result = validateHistoryClaim(singularContract, { total: 3, counts_by_entity: { 'sensor.front_doorbell_last_activity': 2 }, text: 'HA-observed 3', qualified: true });
  assert.ok(result.errors.some(e => e.startsWith('per_entity_sum_mismatch')));
});

test('singular request can never be answered from two devices', () => {
  const broadened = buildHistoryContract({
    plan: singularPlan,
    resolution: { matched: catalog, problems: ['scope_broadened: one device requested'] },
    rows,
    evidenceClass: EVIDENCE.OBSERVED_METADATA,
  });
  const result = validateHistoryClaim(broadened, { total: broadened.total, text: 'HA-observed Front Doorbell Timestamp and Front Driveway Timestamp 3 events', qualified: true });
  assert.ok(result.errors.some(e => e.startsWith('scope_unresolved')));
  assert.ok(result.errors.includes('scope_broadened_for_singular_request'));
});

test('a zero result from observed metadata is scoped to the source, not absolute', () => {
  const empty = buildHistoryContract({
    plan: singularPlan,
    resolution: singularResolution,
    rows: [],
    evidenceClass: EVIDENCE.OBSERVED_METADATA,
  });
  const absolute = validateHistoryClaim(empty, { total: 0, text: 'There were no motion events yesterday.', qualified: true });
  assert.ok(absolute.errors.some(e => e.startsWith('unqualified_absence')), JSON.stringify(absolute.errors));
  const scoped = validateHistoryClaim(empty, { total: 0, text: 'No motion events were recorded within the HA recorder for 2026-10-31.', qualified: true, window_stated: true });
  assert.equal(scoped.ok, true, JSON.stringify(scoped.errors));
});

test('answer scope must match the requested window and event type', () => {
  const route = decideHistoryRoute('Show me the front doorbell motion recordings from yesterday', { now: NOW, catalog });
  assert.deepEqual(answerScopeErrors(route, singularContract), []);
  const wrongWindow = { ...singularContract, window: { ...singularContract.window, date: '2026-10-30' } };
  assert.ok(answerScopeErrors(route, wrongWindow).includes('answer_window_differs_from_request'));
  const wrongType = { ...singularContract, requested: { ...singularContract.requested, event_kinds: ['ding'] } };
  assert.ok(answerScopeErrors(route, wrongType).some(e => e.startsWith('answer_event_type_differs_from_request')));
});

test('renderer states scope, provenance, exclusions and limitation', () => {
  const contract = buildHistoryContract({
    plan: singularPlan,
    resolution: singularResolution,
    rows,
    evidenceClass: EVIDENCE.OBSERVED_METADATA,
    excluded: [{ reason: 'not_ding' }, { reason: 'initial_state_before_window' }],
    artifact: 'evidence/doorbell-2026-10-31.md',
    timeZone: TZ,
  });
  const text = renderHistoryAnswer(contract);
  assert.match(text, /Front Doorbell Timestamp/);
  assert.match(text, /HA-observed metadata/);
  assert.match(text, /2026-10-31/);
  assert.match(text, /Excluded: 1 not ding, 1 initial state before window/);
  assert.match(text, /Limitation:/);
  assert.match(text, /09:46:00/);
  assert.doesNotMatch(text, /authoritative/i);
});

test('normalizeRows converts UTC to local and keeps stable ordering fields', () => {
  const [row] = normalizeRows([{ entity_id: 'x.y', created_at: '2026-10-31T23:08:23Z', category: 'motion' }], { timeZone: TZ });
  assert.equal(row.at_local, '2026-10-31 16:08:23');
  assert.equal(row.at_utc, '2026-10-31T23:08:23.000Z');
});

console.log(`\n${passed} history-contract tests passed`);
