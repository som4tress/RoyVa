# Home Assistant

- Use configured HA MCP tools and their schemas. Do not invent endpoints,
  entities or credentials, or bypass MCP through shell, webfetch or direct APIs.
  Report connection failures or unavailable capabilities; do not change the connection.
- Status and discovery are read-only. Control devices only for a user-requested
  action or an explicitly authorized existing automation instruction.
- Discover first, then control the resolved device. If the first pass finds no
  match, stop control attempts and perform deeper read-only device/entity registry
  discovery before any further control call or claiming "not found". GetLiveContext
  covers only Assist-exposed entities. Never use control tools as discovery probes
  or repeat equivalent failed calls.
- After one unsuccessful direct discovery pass, use Code Mode for read-only
  registry discovery (for example ha_get_device or ha_get_entity) before any
  further device-control tool call. Do not use Code Mode to bypass MCP tools.
- A user may call a switch a "light", or a light a "switch". For missing or
  ambiguous targets, check both light and switch entities, names, aliases and areas;
  select the actual entity and matching control tool from discovery results.
  Never guess entity IDs or broaden an action after a failed lookup. If discovery
  still leaves multiple plausible targets, ask; if none match, explain the limitation.
- Fetch date/time only when needed. A request to act later authorizes scheduling,
  not immediate execution. Cancel only the requested automation or timer.
- Before configuration, scheduling, camera/integration or historical-data tasks,
  use the file-read tool to read the relevant section of
  /home/somdutta/Documents/Codex/opencode-clean/integrations/telegram/ha-guide.md.
  Also load it after an unsuccessful first discovery pass. Before configuration
  writes, read MCP ha_get_skill_guide and follow its requirements.
