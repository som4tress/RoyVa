const direct = new Set([
  'ha_config_set_automation',
  'ha_config_get_automation',
  'ha_config_remove_automation',
  'ha_get_skill_guide',
  'ha_get_device',
  'ha_get_entity',
  'ha_get_integration',
  'ha_get_history',
]);

export default {
  id: 'royva.ha-config-access',
  async setup(ctx) {
    await ctx.tool.transform(editor => {
      for (const tool of editor.list()) {
        if (tool.options?.namespace !== 'home-assistant-config' || !direct.has(tool.name)) continue;
        editor.update(tool.id, current => {
          current.options = {...current.options, codemode: false};
        });
      }
    });
  },
};
