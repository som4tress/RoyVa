import assert from 'node:assert/strict';
import {
  decideHistoryRoute, toolPolicyFor, toolAllowedFor, budgetNotice, answerScopeErrors, isWriteTool,
  filterToolDefinitions, generalBudgetApplies, shouldSwitchModelOnBudget,
} from '../src/lib/history-routing.mjs';

const NOW = Date.parse('2026-11-01T18:00:00Z');
const catalog = [
  { entity_id: 'sensor.front_doorbell_last_activity', name: 'Front Doorbell Timestamp', domain: 'sensor', device_name: 'Front Doorbell' },
  { entity_id: 'sensor.front_driveway_last_activity', name: 'Front Driveway Timestamp', domain: 'sensor', device_name: 'Front Driveway' },
  { entity_id: 'camera.front_doorbell_live_view', name: 'Front Doorbell', domain: 'camera', device_name: 'Front Doorbell' },
  { entity_id: 'camera.front_driveway_live_view', name: 'Front Driveway', domain: 'camera', device_name: 'Front Driveway' },
];
let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log('ok - ' + name); };

test('entity history is an investigation that keeps general read tools', () => {
  const route = decideHistoryRoute('How many motion-triggered Ring recordings were there yesterday, along with their times?', { now: NOW, catalog });
  assert.equal(route.kind, 'investigation');
  assert.equal(route.history_class, 'entity_event_history');
  assert.equal(route.requires_general_tools, true);
  assert.equal(route.allow_writes, false);
  assert.equal(route.evidence_class, 'observed_metadata');
  assert.equal(route.plan.window.date, '2026-10-31');
  const policy = toolPolicyFor(route, 'local');
  assert.equal(policy.strip_non_mcp, false);
  assert.equal(policy.allow_general, true);
  assert.equal(toolAllowedFor(route, 'shell'), true);
  assert.equal(toolAllowedFor(route, 'read'), true);
  assert.equal(toolAllowedFor(route, 'ha-event-history_get_entity_history'), true);
  assert.equal(toolAllowedFor(route, 'ha-history_get_device_status_report'), true);
});

test('no history route can write or actuate media', () => {
  const route = decideHistoryRoute('front doorbell motion recordings yesterday', { now: NOW });
  for (const tool of [
    'home-assistant_intent__HassTurnOn',
    'home-assistant_intent__HassTurnOff',
    'home-assistant_light__HassLightSet',
    'home-assistant_media_player__play_media',
    'home-assistant_assist_satellite__HassBroadcast',
  ]) {
    assert.equal(toolAllowedFor(route, tool), false, tool);
    assert.equal(isWriteTool(tool), true, tool);
  }
});

test('person visit history keeps the narrow zone tool and drops general tools', () => {
  const route = decideHistoryRoute('Where did Shobha go yesterday', { now: NOW });
  assert.equal(route.kind, 'history');
  assert.equal(route.history_class, 'person_location');
  assert.equal(route.requires_general_tools, false);
  const policy = toolPolicyFor(route, 'local');
  assert.equal(policy.strip_non_mcp, true);
  assert.equal(policy.allow_general, false);
  assert.equal(toolAllowedFor(route, 'ha-history_get_visited_locations'), true);
  assert.equal(toolAllowedFor(route, 'shell'), false);
});

test('local 30s hands over to a fresh cloud budget without replaying results', () => {
  const route = decideHistoryRoute('doorbell motion recordings yesterday', { now: NOW, generalLocalMs: 30000, cloudMs: 120000 });
  assert.equal(route.local_budget_ms, 30000);
  assert.equal(route.cloud_budget_ms, 120000);
  assert.equal(route.cloud_budget_is_fresh, true);
  assert.equal(route.preserve_completed_results, true);
  const notice = budgetNotice({ elapsed_ms: 30000, local_budget_ms: 30000, steps: 7, max_steps: 6 });
  assert.match(notice, /fresh budget/);
  assert.match(notice, /must not replay completed writes/);
  assert.doesNotMatch(notice, /tool limit|no tool|capability/i);
});

test('scope is resolved against the catalog and ambiguity is surfaced', () => {
  const singular = decideHistoryRoute('Show me the front doorbell motion recordings from yesterday', { now: NOW, catalog });
  assert.equal(singular.needs_clarification, false);
  assert.equal(singular.resolution.matched.length, 1);
  const ambiguous = decideHistoryRoute('Show me the front camera motion recordings from yesterday', { now: NOW, catalog });
  assert.equal(ambiguous.needs_clarification, true);
  assert.ok(ambiguous.scope_errors.includes('scope_broadened'));
});

test('routing is generic: no household, room or brand literal is required', () => {
  const arbitrary = decideHistoryRoute('show me the north gate sensor motion events yesterday', { now: NOW, catalog });
  assert.equal(arbitrary.kind, 'investigation');
  assert.equal(arbitrary.needs_clarification, true, 'unknown device must be unresolved, not substituted');
  const personArbitrary = decideHistoryRoute('Where was Somdutta yesterday', { now: NOW });
  assert.equal(personArbitrary.history_class, 'person_location');
});

test('answer scope errors catch a broadened or retyped answer', () => {
  const route = decideHistoryRoute('Show me the front doorbell motion recordings from yesterday', { now: NOW, catalog });
  const contract = {
    window: route.plan.window,
    requested: { event_kinds: ['motion'] },
    resolved: { entities: [{ entity_id: 'sensor.front_doorbell_last_activity', name: 'Front Doorbell Timestamp' }] },
  };
  assert.deepEqual(answerScopeErrors(route, contract), []);
  assert.ok(answerScopeErrors(route, { ...contract, window: { date: '2026-10-29' } }).includes('answer_window_differs_from_request'));
  assert.ok(answerScopeErrors(route, { ...contract, resolved: { entities: [...contract.resolved.entities, { entity_id: 'other', name: 'Other' }] } }).includes('answer_broadened_singular_request'));
});

test('a pronoun follow-up is allowed to resolve from the immediate exchange only', () => {
  const followup = decideHistoryRoute('Show me its history', { now: NOW });
  assert.equal(followup.kind, 'investigation');
  assert.equal(followup.followup_reference, true);
  assert.equal(followup.needs_clarification, false);
  assert.ok(followup.plan.followupReference);
  const bare = decideHistoryRoute('Show me the history', { now: NOW });
  assert.equal(bare.needs_clarification, true);
});

const TOOL_CATALOG = [
  'shell', 'read', 'grep', 'glob', 'write', 'edit', 'bash', 'webfetch', 'task',
  'home-assistant_homeassistant__GetLiveContext',
  'home-assistant_intent__HassTurnOn',
  'home-assistant_intent__HassTurnOff',
  'home-assistant_light__HassLightSet',
  'home-assistant_media_player__play_media',
  'ha-history_get_visited_locations',
  'ha-event-history_get_entity_history',
  'ha-event-history_find_history_sources',
];

test('the emitted tool catalog keeps general tools for a clean investigation', () => {
  const route = decideHistoryRoute('front doorbell motion recordings yesterday', { now: NOW });
  const { kept, removed } = filterToolDefinitions(route, TOOL_CATALOG);
  for (const name of ['shell', 'read', 'grep', 'glob', 'webfetch', 'ha-history_get_visited_locations', 'ha-event-history_get_entity_history']) {
    assert.ok(kept.includes(name), name + ' must stay available');
  }
  for (const name of ['home-assistant_intent__HassTurnOn', 'home-assistant_intent__HassTurnOff', 'home-assistant_light__HassLightSet', 'home-assistant_media_player__play_media']) {
    assert.ok(removed.includes(name), name + ' must be removed from a read-only history turn');
  }
});

test('a recalled failed task cannot narrow the investigation tool set', () => {
  const route = decideHistoryRoute('How many ring doorbell events yesterday, along with times', { now: NOW });
  // Simulate the poisoned state: a learned failure points at the person-history tool,
  // and a correction record is attached to this topic.
  const poisoned = { ...route, learned_route_tool: 'ha-history_get_visited_locations', corrections: ['history-failure-recorded'] };
  const { kept } = filterToolDefinitions(poisoned, TOOL_CATALOG);
  assert.deepEqual(kept, filterToolDefinitions(route, TOOL_CATALOG).kept);
  for (const name of ['shell', 'read', 'grep', 'ha-event-history_get_entity_history']) assert.ok(kept.includes(name));
});

test('person-history route still narrows tools to the zone tool', () => {
  const route = decideHistoryRoute('Where did Shobha go yesterday', { now: NOW });
  const policy = toolPolicyFor(route, 'local');
  assert.equal(policy.strip_non_mcp, true);
  const kept = policy.strip_non_mcp ? TOOL_CATALOG.filter(n => /^ha[-_]history_/.test(n)) : TOOL_CATALOG;
  assert.ok(kept.includes('ha-history_get_visited_locations'));
  assert.ok(!kept.includes('shell'));
});

test('a skipped scope never loses its wall-clock budget', () => {
  assert.equal(generalBudgetApplies({ requestKind: 'investigation' }), true);
  assert.equal(generalBudgetApplies({ deterministicKind: 'investigation', semanticKind: null }), true, 'classifier timeout must not skip the timer');
  assert.equal(generalBudgetApplies({ semanticKind: 'investigation', requestKind: 'investigation' }), true);
  assert.equal(generalBudgetApplies({ requestKind: 'devices' }), false);
  assert.equal(generalBudgetApplies({ semanticKind: 'configuration' }), false);
  assert.equal(generalBudgetApplies({ hasFiles: true, requestKind: 'investigation' }), false);
  assert.equal(generalBudgetApplies({ forbidden: true, requestKind: 'investigation' }), false);
  assert.equal(generalBudgetApplies({}), true, 'unknown general work still gets a local-first budget');
});

test('a completed idle session is not switched by the watchdog', () => {
  const startedAt = 1000;
  assert.equal(shouldSwitchModelOnBudget({ idleAt: 2000, busyAt: 1000, startedAt }), false);
  assert.equal(shouldSwitchModelOnBudget({ idleAt: 500, busyAt: 2000, startedAt }), true, 'still busy at the deadline');
  assert.equal(shouldSwitchModelOnBudget({ idleAt: 2000, busyAt: 1000, startedAt, alreadyFailed: true }), false);
});

test('non-history text has no history route', () => {
  assert.equal(decideHistoryRoute('turn on the kitchen light', { now: NOW }), null);
  assert.equal(decideHistoryRoute('what is the stock price', { now: NOW }), null);
  assert.equal(decideHistoryRoute('', { now: NOW }), null);
});

console.log(`\n${passed} history-routing tests passed`);
