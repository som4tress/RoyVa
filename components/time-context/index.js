const timeZone = 'America/Los_Angeles';
const marker = '<royva-time-context>';

export function timeContext(now = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now).map(part => [part.type, part.value]));
  return `${marker}\nCurrent local date: ${parts.year}-${parts.month}-${parts.day}\nTime zone: ${timeZone}\n“Today” refers to this local date. For current information, use this year unless the user specifies another date or period.\n</royva-time-context>`;
}

export default {
  id: 'royva.time-context',
  async setup(ctx) {
    const refresh = event => {
      event.system = event.system.filter(part => !(part.type === 'text' && part.text.startsWith(marker)));
      event.system.push({type: 'text', text: timeContext()});
    };
    for (const hook of ['context', 'compaction', 'generate']) {
      await ctx.session.hook(hook, refresh);
    }
  },
};
