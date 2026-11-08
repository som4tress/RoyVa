# Legacy HA interfaces used for evaluation

The stdio transport connects to Home Assistant's native MCP (19 tools).
The separate read-only helper exposes visited locations and current-state reports.
Only these interfaces are restored; old gateway plugins, prompts and routing are not loaded.

The history helper selects person entities for three fixed household choices.
It accepts timezone-aware start/end datetimes for the full requested window;
end may be omitted for now. There is no seven-day tool limit. The default
places view returns all distinct named zones, interval counts, and first/last
observations. The intervals view retains chronological named-zone intervals
and transit/unknown gaps. Consecutive identical states are merged by CPU code.
A named-zone crossing is not proof of a stop; retention and tracking gaps can
limit the evidence. Requests use one HA recorder query for the full window.

Private connection details remain in ~/llm-server/ha-remote.json and the HA_TOKEN
in ~/llm-server/ha.env. No credentials or connection files are included here.
The copied helpers read that private connection file directly, avoiding dependency
on the old OpenCode configuration. The new ha-mcp remains available under
home-assistant-config for configuration work; its overlapping state, history,
overview, search and service-call tools are denied in the OpenCode configuration.
