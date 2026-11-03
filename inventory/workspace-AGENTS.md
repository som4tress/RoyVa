# Jarvis runtime version control

All Jarvis/OpenCode runtime work must follow the change workflow in
`/home/somdutta/Documents/Codex/jarvis-runtime/AGENTS.md`.

Before editing, check the repository and deployed-source drift. After each
logical code/configuration change, run focused validation, capture deployed
sources, review the diff, and make a descriptive Git commit. Do not leave
uncommitted runtime changes at handoff. Keep secrets and runtime data out of Git.

Do not confuse the pinned upstream OpenCode checkout with the running binary.
Record version/hash changes when upgrading. Do not push without user direction.
