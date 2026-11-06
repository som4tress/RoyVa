import test from 'node:test';
import assert from 'node:assert/strict';
import plugin, {timeContext} from './index.js';

test('uses local calendar date across UTC midnight, new year, and DST', () => {
  for (const [instant, expected] of [
    ['2026-11-06T00:30:00Z', '2026-11-05'],
    ['2027-01-01T07:59:59Z', '2026-12-31'],
    ['2027-01-01T08:00:00Z', '2027-01-01'],
    ['2026-03-08T09:59:59Z', '2026-03-08'],
    ['2026-03-08T10:00:00Z', '2026-03-08'],
    ['2026-11-01T08:59:59Z', '2026-11-01'],
    ['2026-11-01T09:00:00Z', '2026-11-01'],
  ]) assert(timeContext(new Date(instant)).includes(`Current local date: ${expected}`));
});

test('refreshes each generation, appends after stable system text, and never accumulates', async () => {
  const hooks = new Map();
  await plugin.setup({session: {hook: async (name, fn) => hooks.set(name, fn)}});
  const stable = {type: 'text', text: 'Stable instructions'};
  const messages = [{role: 'user', content: 'Historical question'}];
  const tools = {websearch: {}};
  const event = {system: [stable, {type: 'text', text: '<royva-time-context>\nStale date'}], messages, tools};
  for (const hook of ['context', 'compaction', 'generate', 'context']) {
    await hooks.get(hook)(event);
    assert.equal(event.system.length, 2);
    assert.equal(event.system[0], stable);
    assert.equal(event.system[1].text, timeContext());
    assert.equal(event.messages, messages);
    assert.equal(event.tools, tools);
  }
});

test('an existing session receives the new date after local midnight', async context => {
  context.mock.timers.enable({apis: ['Date'], now: new Date('2026-11-06T07:59:59Z')});
  const hooks = new Map();
  await plugin.setup({session: {hook: async (name, fn) => hooks.set(name, fn)}});
  const event = {system: []};
  hooks.get('context')(event);
  assert(event.system[0].text.includes('Current local date: 2026-11-05'));
  context.mock.timers.tick(2000);
  hooks.get('context')(event);
  assert.equal(event.system.length, 1);
  assert(event.system[0].text.includes('Current local date: 2026-11-06'));
});
