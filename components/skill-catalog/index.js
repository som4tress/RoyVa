export default {
  id: 'royva.skill-catalog',
  async setup(ctx) {
    const constrain = async (event) => {
      const tool = event.tools.skill;
      if (!tool) return;
      const { data } = await ctx.skill.list();
      const ids = data.map(skill => skill.id).sort();
      if (!ids.length) {
        delete event.tools.skill;
        return;
      }
      tool.input = {
        type: 'object',
        properties: { id: { type: 'string', enum: ids } },
        required: ['id'],
        additionalProperties: false,
      };
    };
    for (const hook of ['context', 'compaction', 'generate']) {
      await ctx.session.hook(hook, constrain);
    }
  },
};
