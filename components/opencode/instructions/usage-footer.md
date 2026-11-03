# Usage reporting
Telegram appends a usage footer in code after a completed invocation, using only that invocation's assistant message IDs and linked subagent messages. Do not run a usage script or manufacture a footer while generating a normal reply: that adds another model call and cannot include its own final cost. Local, free-provider and zero-inference turns have no paid OpenRouter footer. Other OpenCode frontends retain their native usage display; do not invent per-request figures.
For an explicit usage query, use scripts/openrouter-usage with --session and either --message-ids or a bounded --since-ms/--until-ms window. It is stateless and does not consume a shared cursor. The footer also carries the account total and remaining credit (`total $3.46/$10.00 · $6.54 left`); that balance is account-wide, never the per-turn cost.

For an explicitly requested account balance, run scripts/openrouter-usage --account. This is separate account-wide usage, never the per-turn cost.
