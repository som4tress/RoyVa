import test from 'node:test';
import assert from 'node:assert/strict';
import plugin from './index.js';

test('uses the current catalogue on each request and leaves unrelated tools intact', async () => {
  const hooks = new Map();
  let data = [{id: 'report'}, {id: 'opencode'}];
  await plugin.setup({skill: {list: async () => ({data})}, session: {hook: async (name, fn) => hooks.set(name, fn)}});
  assert.deepEqual([...hooks.keys()], ['context', 'compaction', 'generate']);
  const other = {description: 'Unchanged', input: {type: 'object'}};
  const event = () => ({tools: {skill: {description: 'Load skill', input: {type: 'object'}}, other}});
  let request = event();
  await hooks.get('context')(request);
  assert.deepEqual(request.tools.skill.input.properties.id.enum, ['opencode', 'report']);
  assert.equal(request.tools.skill.description, 'Load skill');
  assert.equal(request.tools.other, other);
  assert(!request.tools.skill.input.properties.id.enum.includes('home-assistant'));
  data = [{id: 'newly-installed'}];
  request = event();
  await hooks.get('compaction')(request);
  assert.deepEqual(request.tools.skill.input.properties.id.enum, ['newly-installed']);
  data = [];
  request = event();
  await hooks.get('generate')(request);
  assert(!('skill' in request.tools));
  assert.equal(request.tools.other, other);
  await hooks.get('context')({tools: {other}});
});
