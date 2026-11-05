# Home Assistant tool access

For Home Assistant questions and actions, use the configured home-assistant MCP
tools. Use the tools' advertised argument schemas and returned entity information.
Do not invent Home Assistant URLs, localhost endpoints, entity identities or tokens,
or bypass the MCP tools using webfetch, shell commands, fetch code or direct APIs.
If the available MCP tools cannot perform the requested task, explain that limitation.
If a tool reports a connection failure, report it rather than attempting an alternative
connection or changing the integration. This rule applies only to Home Assistant.
