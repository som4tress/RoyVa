import test from 'node:test';
import assert from 'node:assert/strict';
import plugin from './index.js';
test('only changes exposure of selected config tools, preserving execution and permissions', async () => {
  const execute = () => {};
  const tools = [
    ...['ha_config_set_automation', 'ha_config_get_automation', 'ha_config_remove_automation', 'ha_get_skill_guide', 'ha_get_device', 'ha_get_entity', 'ha_get_integration', 'ha_get_history', 'ha_config_get_label'].map(name => ({id: name, name, options: {namespace: 'home-assistant-config', permission: name, codemode: true}, execute})),
    {id: 'other', name: 'ha_config_set_automation', options: {namespace: 'other', codemode: true}, execute},
  ];
  await plugin.setup({tool: {transform: async fn => fn({list: () => tools, update: (id, fn) => fn(tools.find(t => t.id === id))})}});
  assert(tools.slice(0, 8).every(t => t.options.codemode === false));
  assert(tools.slice(8).every(t => t.options.codemode === true));
  assert(tools.every(t => t.execute === execute));
  assert.equal(tools[0].options.permission, 'ha_config_set_automation');
});
