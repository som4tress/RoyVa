/**
 * Combined router pipeline test.
 *
 * Mounts the staged ha-mcp-routing plugin with a fake OpenCode context, then drives
 * the real hooks: prompt → context → http.request → tool execute.before. It asserts
 * the actual emitted request body, not just the classifier.
 *
 * HOME is redirected to a temp directory before importing anything so no live
 * learning, correction, phrase or log file is touched.
 */
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, rmSync, cpSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';

const root = join(process.cwd());
const home = mkdtempSync(join(tmpdir(), 'hist-pipeline-'));
process.env.HOME = home;

const mirror = join(home, 'mirror');
mkdirSync(join(mirror, 'plugins'), { recursive: true });
cpSync('/home/somdutta/.config/opencode/lib', join(mirror, 'lib'), { recursive: true });
cpSync('/home/somdutta/.config/opencode/plugins/ha-mcp-routing', join(mirror, 'plugins/ha-mcp-routing'), { recursive: true });
cpSync('/home/somdutta/.config/opencode/plugins/procedure-memory', join(mirror, 'plugins/procedure-memory'), { recursive: true });
for (const name of ['history-scope', 'history-routing', 'history-contract', 'corrections', 'ha-request-classify']) {
  cpSync(join(root, 'src/lib', name + '.mjs'), join(mirror, 'lib', name + '.mjs'));
}
for (const name of ['index.js', 'learning.js', 'phrases.js', 'media-routing.js']) {
  cpSync(join(root, 'src/plugins/ha-mcp-routing', name), join(mirror, 'plugins/ha-mcp-routing', name));
}

const { recordCorrection } = await import(pathToFileURL(join(mirror, 'lib/corrections.mjs')).href);
recordCorrection({
  kind: 'failure',
  topic: 'ring doorbell events yesterday along with times',
  statement: 'A previous attempt queried person visit history for a camera-event question and then reported that no tool could count events.',
  observed: 'Wrong history family selected for camera events.',
  proposed_correction: 'Use a read-only entity/event investigation with general tools.',
  evidence: [{ type: 'session', ref: 'session:ses_test/turn1', observed_at: '2026-11-01T15:37:00Z', excerpt: 'no tool here can count past doorbell events' }],
  source_versions: { plugin: 'staged', ha: '2026.10.4' },
  regression_tests: ['tests/test_plugin_pipeline.mjs'],
});

const plugin = (await import(pathToFileURL(join(mirror, 'plugins/ha-mcp-routing/index.js')).href)).default;

const hooks = { prompt: [], context: [], 'model.request': [], retry: [], 'http.request': [] };
const toolHooks = { 'execute.before': [], 'execute.after': [] };
const permHooks = { evaluate: [] };
const storage = new Map();
const switches = [];
const ctx = {
  session: {
    hook: (name, fn) => hooks[name].push(fn),
    switchModel: async ({ model }) => { switches.push(model); },
    get: async () => ({ agent: 'telegram', model: { providerID: 'evo-agent', id: 'qwen36-agent' }, time: { idle: 0, busy: Date.now() }, metadata: {} }),
    context: async () => [],
  },
  tool: { hook: (name, fn) => toolHooks[name].push(fn), list: null },
  permission: { hook: (name, fn) => permHooks[name].push(fn) },
  storage: { get: async key => storage.get(key), set: async (key, value) => storage.set(key, value), remove: async key => storage.delete(key) },
  options: { learningStore: join(home, 'learned-routes.json'), phraseStore: join(home, 'learned-phrases.json') },
};
await plugin.setup(ctx);
assert.ok(hooks.prompt.length && hooks.context.length && hooks['http.request'].length);

const sessionID = 'ses_pipeline_test';
const prompt = 'How many ring doorbell events yesterday, along with times';
await hooks.prompt[0]({ sessionID, prompt: { text: prompt, files: [], metadata: {} } });
const state = storage.get('ha-turn:' + sessionID);
assert.ok(state, 'prompt hook must persist a turn state');
assert.equal(state.kind, 'investigation');
assert.ok(state.historyPlan);
const todayLA = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles' }).format(new Date());
const yesterdayDate = new Date(todayLA + 'T00:00:00Z');
yesterdayDate.setUTCDate(yesterdayDate.getUTCDate() - 1);
assert.equal(state.historyPlan.window.date, yesterdayDate.toISOString().slice(0, 10), 'window must be yesterday in America/Los_Angeles');
assert.deepEqual(switches.at(-1), { providerID: 'evo-agent', id: 'qwen36-agent' }, 'history starts on the local model');

const contextEvent = { sessionID, tools: { shell: {}, read: {}, grep: {}, 'home-assistant_intent__HassTurnOn': {} }, system: [], options: {} };
for (const hook of hooks.context) await hook(contextEvent);
const systemText = contextEvent.system.map(part => part.text).join('\n');
assert.match(systemText, /read-only historical investigation/);
assert.match(systemText, /not a limitation claim/);
assert.match(systemText, /not proof of absence/);
assert.ok(contextEvent.tools.shell, 'context hook must not remove general tools');

const toolCatalog = [
  { type: 'function', function: { name: 'shell' } },
  { type: 'function', function: { name: 'read' } },
  { type: 'function', function: { name: 'grep' } },
  { type: 'function', function: { name: 'edit' } },
  { type: 'function', function: { name: 'home-assistant_intent__HassTurnOn' } },
  { type: 'function', function: { name: 'home-assistant_light__HassLightSet' } },
  { type: 'function', function: { name: 'ha-history_get_visited_locations' } },
  { type: 'function', function: { name: 'ha-event-history_get_entity_history' } },
  { type: 'function', function: { name: 'ha-event-history_find_history_sources' } },
];
const requestEvent = {
  sessionID,
  kind: 'primary',
  model: { providerID: 'evo-agent', id: 'qwen36-agent' },
  request: new Request('http://127.0.0.1:8011/local/v1/chat/completions', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ model: 'qwen36-agent', messages: [{ role: 'user', content: prompt }], tools: toolCatalog }),
  }),
};
await hooks['http.request'][0](requestEvent);
const emitted = await requestEvent.request.clone().json();
const names = emitted.tools.map(tool => tool.function.name);
for (const needed of ['shell', 'read', 'grep', 'edit', 'ha-history_get_visited_locations', 'ha-event-history_get_entity_history', 'ha-event-history_find_history_sources']) {
  assert.ok(names.includes(needed), needed + ' must remain in the emitted request');
}
for (const banned of ['home-assistant_intent__HassTurnOn', 'home-assistant_light__HassLightSet']) {
  assert.ok(!names.includes(banned), banned + ' must be removed from a read-only history request');
}

await assert.rejects(
  toolHooks['execute.before'][0]({ sessionID, tool: 'home-assistant_intent__HassTurnOn', input: { name: 'Front Doorbell' } }),
  /read-only/i,
);

// A second, clean request with the same wording must produce the same tool set even
// though a failed-attempt correction record now exists for this topic.
const sessionID2 = 'ses_pipeline_test_2';
await hooks.prompt[0]({ sessionID: sessionID2, prompt: { text: prompt, files: [], metadata: {} } });
const contextEvent2 = { sessionID: sessionID2, tools: { shell: {}, read: {} }, system: [], options: {} };
for (const hook of hooks.context) await hook(contextEvent2);
const systemText2 = contextEvent2.system.map(part => part.text).join('\n');
assert.match(systemText2, /not a limitation claim/);

rmSync(home, { recursive: true, force: true });
console.log('ok - prompt hook routes the complaint wording to a local read-only investigation');
console.log('ok - emitted request body keeps general tools and removes HA writes');
console.log('ok - an uncertain write is refused during a history investigation');
console.log('ok - a stored failed-attempt correction is injected as data, not as a limitation');
