# Skill catalogue constraint

An OpenCode V2 Promise plugin using supported session hooks. On each primary,
compaction or generation request, the skill tool's ID schema is an enum of
currently installed skill IDs. With no skills it is omitted. Other tools,
system instructions and existing execution/permission checks are unchanged.
No household names or guessed skill aliases are hardcoded. The catalogue is
read afresh so installed/removed skills are reflected without maintaining a list.

This narrows the model-facing contract; it is not a guarantee that every model
will obey the schema. Unknown IDs still fail existing OpenCode validation.
No prompt text, automatic retries or skill-name substitutions are added.
