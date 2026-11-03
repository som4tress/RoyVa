# Royva runtime version control

All Royva/OpenCode runtime work must follow the change workflow in
`/home/somdutta/Documents/Codex/royva/AGENTS.md`.

Before editing, check the repository and deployed-source drift. Run focused
validation, capture deployed sources, and review the diff. Commit only when the
user explicitly requests it for the current change. Do not commit test results
or benchmark reports unless specifically authorized. Keep secrets and runtime
data out of Git.

Do not confuse the pinned upstream OpenCode checkout with the running binary.
Record version/hash changes when upgrading. Do not push without user direction.
