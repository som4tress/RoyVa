import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import {
  recordCorrection, recordFailure, promoteToValidated, supersedeCorrection,
  findCorrections, correctionHint, listCorrections,
  STORE_PATH, PROCEDURE_STORE, TASK_STORE, SCHEMA_VERSION,
} from '../src/lib/corrections.mjs';

let passed = 0;
const test = async (name, fn) => { await fn(); passed++; console.log('ok - ' + name); };
const dir = mkdtempSync(join(tmpdir(), 'corrections-test-'));
const store = join(dir, 'index.json');
const observedAt = '2026-10-31T18:00:00Z';

const evidence = (ref = 'session:ses_test/tool:ha-history_get_visited_locations') => ([
  { type: 'tool_result', ref, observed_at: observedAt, excerpt: 'returned person zone rows for a camera-event question' },
]);

await test('failure records are stored separately from procedures and tasks', () => {
  assert.notEqual(store, PROCEDURE_STORE);
  assert.notEqual(store, TASK_STORE);
  assert.ok(!store.includes('/procedures/'));
  recordFailure({
    task: 'How many ring doorbell events yesterday, along with times',
    observed: 'The history route called person visit history and then declared that no tool could count camera events.',
    evidence: evidence(),
    source_versions: { plugin: 'ha-mcp-routing@live-2026-11-01', ha: '2026.10.4' },
    scope: { device_class: 'camera', event: 'motion', window: 'local_day' },
    proposed_correction: 'Route device/event history to a read-only investigation that keeps general tools.',
    regression_tests: ['tests/test_request_classify.mjs', 'tests/test_history_routing.mjs'],
  }, store);
  const record = JSON.parse(readFileSync(store, 'utf8')).records[0];
  assert.equal(record.kind, 'failure');
  assert.equal(record.validation_status, 'proposed');
  assert.equal(record.confidence, 'low');
  assert.equal(record.source_versions.ha, '2026.10.4');
  assert.deepEqual(record.scope, { device_class: 'camera', event: 'motion', window: 'local_day' });
  assert.ok(record.task_family);
  assert.ok(record.observed);
  assert.match(record.proposed_correction, /read-only investigation/);
  assert.equal(record.auto_executable, false);
  assert.ok(record.regression_tests.includes('tests/test_history_routing.mjs'));
  assert.ok(record.preconditions.some(p => /not a validated capability statement/.test(p)));
  assert.ok(!existsSync(join(dir, 'procedures.json')));
  assert.ok(!existsSync(join(dir, 'tasks.json')));
  assert.ok(existsSync(join(dir, 'archive.jsonl')), 'corrections apply an append-only archive');
});

await test('corrections cannot be stored as executable commands', () => {
  assert.throws(() => recordCorrection({ kind: 'failure', statement: 'Observed failure.', evidence: evidence(), command: 'curl ...' }, store), /auto-executable|executable/i);
  assert.throws(() => recordCorrection({ kind: 'failure', statement: 'Observed failure.', evidence: evidence(), auto_executable: true }, store), /auto-executable|executable/i);
});

await test('a correction without evidence is refused', () => {
  assert.throws(() => recordCorrection({ kind: 'capability', statement: 'Entity history is unavailable.' }, store), /evidence/i);
  assert.throws(() => recordCorrection({ kind: 'capability', statement: 'No evidence here.', evidence: [{ type: 'tool', ref: '', observed_at: observedAt }] }, store), /evidence/i);
});

await test('absolute limitation wording is refused at write time', () => {
  for (const statement of [
    'No tool can count Ring recordings.',
    'It is impossible to read camera history.',
    'There is no way to get provider clips.',
  ]) {
    assert.throws(() => recordCorrection({ kind: 'capability', statement, evidence: evidence() }, store), /Absolute limitation/);
  }
});

await test('a validated record needs independent evidence', () => {
  assert.throws(() => recordCorrection({
    kind: 'name_mapping',
    statement: 'The irrigation integration is exposed under Smart Outdoor Timer entity names.',
    evidence: evidence(),
    validation_status: 'validated',
  }, store), /independent/i);
});

await test('an observed alias correction is stored with preconditions and recheck state', () => {
  const record = recordCorrection({
    kind: 'name_mapping',
    topic: 'bhyve irrigation watering history alias',
    statement: 'A source lookup for "bhyve" matched no entity, while the irrigation integration is exposed as Smart Outdoor Timer switches, valves and an Orbit BHyve update entity. Alias resolution is required before concluding the integration is absent.',
    scope: { integration: 'irrigation', entity_domains: ['switch', 'valve', 'update'] },
    preconditions: ['Only the exact word "bhyve" was searched; the entity catalog was not enumerated.'],
    evidence: [
      { type: 'tool_result', ref: 'tool:ha-history_find_history_sources:{"query":"bhyve"}', observed_at: observedAt, excerpt: 'total_candidates: 0' },
      { type: 'independent_read', ref: 'ha:/api/states?filter=smart_outdoor_timer', observed_at: observedAt, excerpt: '11 switch/valve entities plus update.orbit_bhyve_update', independent: true },
    ],
    validation_status: 'validated',
    validation_source: 'independent_read',
    validated_by: 'independent state catalog read',
    source_versions: { ha: '2026.10.4', schema: SCHEMA_VERSION },
    confidence: 'high',
  }, store);
  assert.equal(record.validation_status, 'validated');
  assert.equal(record.recheck_required, false);
  assert.ok(record.evidence.some(e => e.independent));
});

await test('retrieval is topic-scoped and marks recheck for proposed records', () => {
  const hits = findCorrections('How many ring doorbell events yesterday', { path: store });
  assert.ok(hits.length >= 1);
  assert.equal(hits[0].validation_status, 'proposed');
  assert.equal(hits[0].recheck_required, true);
  const hint = correctionHint('How many ring doorbell events yesterday', { path: store });
  assert.match(hint, /not a limitation claim/);
  assert.match(hint, /Verify current capability/);
  assert.match(hint, /Never restate a proposed or expired record as impossibility/);
  const unrelated = findCorrections('turn on the kitchen light', { path: store });
  assert.equal(unrelated.length, 0);
});

await test('expired records are not retrieved', () => {
  recordCorrection({
    kind: 'count_provenance',
    topic: 'short lived provenance note',
    statement: 'A proxy pulse count was briefly treated as a recording count.',
    evidence: evidence('tool:pulse-read'),
    ttl_ms: 1000,
  }, store);
  const before = findCorrections('short lived provenance note', { path: store });
  assert.equal(before.length, 1);
  const after = findCorrections('short lived provenance note', { path: store, now: Date.now() + 5000 });
  assert.equal(after.length, 0);
});

await test('promotion requires independent evidence from a different source', () => {
  const failure = recordFailure({
    task: 'front gate camera motion history',
    observed: 'A lookup for the front gate camera returned no entity.',
    evidence: evidence('tool:find_history_sources:{"query":"front gate"}'),
  }, store);
  assert.throws(() => promoteToValidated(failure.id, {
    validation_source: 'independent_read',
    evidence: [{ type: 'independent_read', ref: 'tool:find_history_sources:{"query":"front gate"}', observed_at: observedAt, independent: true }],
  }, store), /different source|independent/i);
  const promoted = promoteToValidated(failure.id, {
    validated_by: 'device registry read',
    validation_source: 'independent_read',
    evidence: [{ type: 'independent_read', ref: 'ha:/api/config/device_registry', observed_at: observedAt, independent: true, excerpt: 'no matching device' }],
  }, store);
  assert.equal(promoted.validation_status, 'validated');
  assert.equal(findCorrections('front gate camera motion history', { path: store })[0].validation_status, 'validated');
});

await test('superseded records disappear from retrieval', () => {
  const old = findCorrections('bhyve irrigation watering history alias', { path: store })[0];
  const replacement = recordCorrection({
    kind: 'name_mapping',
    topic: 'bhyve irrigation watering history alias',
    statement: 'Irrigation history is exposed through Smart Outdoor Timer entities; use a discovered zone entity for recorder reads.',
    evidence: [{ type: 'independent_read', ref: 'ha:/api/states/switch.smart_outdoor_timer_zone_1_garden_smart_watering', observed_at: observedAt, independent: true }],
    validation_status: 'validated',
    validation_source: 'independent_read',
  }, store);
  supersedeCorrection(old.id, { by: replacement.id, reason: 'replaced by a narrower verified statement' }, store);
  assert.ok(!findCorrections('bhyve irrigation watering history alias', { path: store }).some(r => r.id === old.id));
});

await test('secrets are scrubbed and never stored', () => {
  const secret = 'Bearer abcdef0123456789abcdef';
  const record = recordCorrection({
    kind: 'scope',
    topic: 'credential exposure check',
    statement: 'A read used an environment credential without exposing it.',
    evidence: [{ type: 'tool_result', ref: 'tool:read:ha.env', observed_at: observedAt, excerpt: secret }],
  }, store);
  assert.ok(!JSON.stringify(record).includes('abcdef0123456789'));
});

await test('concurrent writes keep a valid store and all records', async () => {
  const concurrent = join(dir, 'concurrent.json');
  await Promise.all(Array.from({ length: 20 }, (_, i) => Promise.resolve().then(() => recordCorrection({
    kind: 'failure',
    topic: 'concurrent failure ' + i,
    statement: 'Concurrent observation ' + i + ' failed until the alias was resolved.',
    evidence: evidence('tool:probe:' + i),
  }, concurrent))));
  const data = JSON.parse(readFileSync(concurrent, 'utf8'));
  assert.equal(data.version, SCHEMA_VERSION);
  assert.equal(data.records.length, 20);
});

await test('listing reports validation state and evidence counts', () => {
  const rows = listCorrections({ path: store });
  assert.ok(rows.length >= 3);
  assert.ok(rows.every(r => ['proposed', 'validated', 'superseded', 'expired'].includes(r.validation_status)));
  assert.ok(rows.every(r => r.evidence_count >= 1));
});

rmSync(dir, { recursive: true, force: true });
console.log(`\n${passed} corrections tests passed`);
