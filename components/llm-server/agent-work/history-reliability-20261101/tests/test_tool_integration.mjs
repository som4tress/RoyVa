import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { parseHistoryRequest, resolveHistoryScope } from '../src/lib/history-scope.mjs';
import { buildHistoryContract, validateHistoryClaim, renderHistoryAnswer, EVIDENCE } from '../src/lib/history-contract.mjs';
import { decideHistoryRoute } from '../src/lib/history-routing.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const NOW = Date.parse('2026-11-01T18:00:00Z');

const script = `
import importlib.util, json, sys
spec=importlib.util.spec_from_file_location("m","${join(root, 'src/mcp/ha_event_history.py').replace(/\\/g, '/')}")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
states=[
 {"entity_id":"sensor.front_doorbell_last_activity","state":"x","attributes":{"friendly_name":"Front Doorbell Timestamp","category":"motion"}},
 {"entity_id":"camera.front_doorbell_live_view","state":"idle","attributes":{"friendly_name":"Front Doorbell"}},
 {"entity_id":"sensor.front_driveway_last_activity","state":"x","attributes":{"friendly_name":"Front Driveway Timestamp","category":"motion"}},
]
def row(t,cat="motion"):
 return {"entity_id":"sensor.front_doorbell_last_activity","state":t,"last_changed":t,"attributes":{"created_at":t,"category":cat,"recording_status":"ready"}}
hist=[
 row("2026-10-31T07:00:00+00:00"),
 row("2026-10-31T16:46:00+00:00"),
 row("2026-10-31T16:47:07+00:00"),
 row("2026-10-31T20:00:00+00:00","on_demand"),
 row("2026-10-31T23:08:23+00:00"),
]
m.read_api=lambda p,timeout=30: states if p=="/api/states" else []
m.ha_version=lambda: "2026.10.4"
m.fetch_history=lambda eid,start,end: hist if eid=="sensor.front_doorbell_last_activity" else []
print(json.dumps(m.collect_history({"name":"front doorbell","date":"2026-10-31","category":["motion"],"recording_status":["ready"]})))
`;
const proc = spawnSync('python3', ['-c', script], { encoding: 'utf8' });
assert.equal(proc.status, 0, proc.stderr);
const tool = JSON.parse(proc.stdout);

assert.equal(tool.evidence_class, 'observed_metadata');
assert.equal(tool.total, 3, JSON.stringify(tool.excluded));
assert.equal(tool.selected_sources.length, 1);
assert.equal(tool.selected_sources[0].entity_id, 'sensor.front_doorbell_last_activity');
assert.equal(tool.selection.unique_key, 'created_at');
assert.equal(tool.selection.attribute_filters.category[0], 'motion');
assert.deepEqual(tool.excluded_sources.map(s => s.entity_id).sort(), ['camera.front_doorbell_live_view']);

const plan = parseHistoryRequest('Show me the front doorbell motion recordings from yesterday', { now: NOW });
const resolution = {
  matched: tool.selected_sources.map(s => ({ ...s, domain: 'sensor', device_name: 'Front Doorbell' })),
  problems: [],
};
const contract = buildHistoryContract({
  plan,
  resolution,
  rows: tool.rows,
  source: tool.source,
  evidenceClass: EVIDENCE.OBSERVED_METADATA,
  timeZone: 'America/Los_Angeles',
  completeness: tool.completeness,
  sourceVersions: tool.source_versions,
  selection: tool.selection,
});
const route = decideHistoryRoute(plan.raw, { now: NOW, catalog: resolution.matched });
assert.equal(route.kind, 'investigation');

const good = validateHistoryClaim(contract, {
  total: tool.total,
  text: 'HA-observed recorder metadata: 3 motion events for Front Doorbell Timestamp on 2026-10-31.',
  qualified: true,
  window_stated: true,
  exclusions_stated: true,
});
assert.equal(good.ok, true, JSON.stringify(good.errors));

const bad = validateHistoryClaim(contract, { total: 114, text: '114 Ring motion recordings.' });
assert.equal(bad.ok, false);
assert.ok(bad.errors.some(e => e.startsWith('count_mismatch')));
assert.ok(bad.errors.some(e => e.startsWith('provenance_unstated')));

const rendered = renderHistoryAnswer(contract);
assert.match(rendered, /\*\*3\*\* motion events/);
assert.match(rendered, /HA-observed metadata/);
assert.match(rendered, /2026-10-31/);
assert.match(rendered, /09:46:00/);
assert.equal(contract.filter_semantics.dedupe_key, 'created_at');
assert.ok(contract.unique_key_definition.includes('created_at'));
assert.doesNotMatch(rendered, /authoritative/i);

console.log('ok - staged MCP history tool output flows into the evidence contract');
console.log('ok - a 114-style unverified aggregate is rejected by the contract');
console.log('ok - the deterministic renderer keeps scope, provenance and window');
