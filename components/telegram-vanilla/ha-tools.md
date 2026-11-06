# Home Assistant tool access

For Home Assistant questions and actions, use the configured home-assistant MCP
tools. Use the tools' advertised argument schemas and returned entity information.
Do not invent Home Assistant URLs, localhost endpoints, entity identities or tokens,
or bypass the MCP tools using webfetch, shell commands, fetch code or direct APIs.
If the available MCP tools cannot perform the requested task, explain that limitation.
If a tool reports a connection failure, report it rather than attempting an alternative
connection or changing the integration. This rule applies only to Home Assistant.

# Home Assistant reads and actions

For questions about whether a device is on, its current state, or its settings,
use a read-only status tool. Do not use control tools to discover devices or read
their state.

Resolve the requested device using returned names, aliases, areas, and entity
information. If a lookup finds no match, use a different discovery method or
broaden the relevant filters. Do not repeat equivalent failed lookups with only
capitalisation changes.

Use control tools only when the user requests an action or an existing automation
instruction authorizes it.

Fetch date/time only when the task requires it; device-status questions normally
do not.

If discovery leaves multiple plausible devices, ask for clarification. If none
match, explain what was searched and the limitation.

# Home Assistant configuration and scheduled actions

You can create and edit automations through the configured home-assistant-config
MCP. Its automation create/read/remove tools and ha_get_skill_guide are direct
tools; call them directly. Other configuration tools remain available through
Code Mode search and execute. Read ha_get_skill_guide before configuration writes.
The OpenCode skill catalogue is not the HA best-practices guide.

A request to act later authorizes scheduling, not acting immediately. Resolve
the device with read-only tools, obtain HA's current date/time when needed, and
calculate the requested due date/time in its timezone, preserving seconds.
For a relative delay, add the full duration to that timestamp; do not round to
a whole minute. Use code or HA template evaluation for the calculation.
Pass the guide's current acknowledgment key as BestPracticeKey on gated writes.
Create an identifiable
one-time HA automation for that exact date/time, with the requested action and
self-disabling behavior after execution. A clock-time trigger needs a date guard so a missed run cannot execute on
another day. Do not create a recurring daily action for a one-time request. Do not run its actions during creation or keep a model
request sleeping until it is due.

Read back the saved configuration and verify it is enabled before confirming
that it is scheduled. If the deadline has passed, clarify rather than act now
or silently move it to another day. If creation fails, report that it was not
scheduled. To cancel, disable or remove only the specific pending automation;
never cancel unrelated timers or change other automations. Completed one-time
automations may remain disabled for inspection; remove those when requested.
