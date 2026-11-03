# Baseline status — 2026-11-03

This checkpoint preserves current behavior before further diagnosis. Earlier
incremental edits cannot be reconstructed as trustworthy historical commits.
Existing source whitespace/line endings are preserved rather than reformatted
as part of the checkpoint.

- A Telegram weather follow-up produced invented forecast values and attributed
  them to an API without executing a retrieval tool. This is a failed test.
- Direct requests to the same local Qwen endpoint with minimal instructions and
  two general web tools chose search successfully. Those first-step checks do
  not validate a full tool workflow or establish a root cause.
- Stock OpenCode has not been demonstrated responsible. Our custom instructions,
  profile filtering, routing, context cleanup, sampling, and model variability
  remain candidates; do not label hypotheses as confirmed causes.
- Current custom completion checks detect question echoes, some unsupported
  capability refusals, and explicit source claims without current-task tool
  evidence. Five focused unit tests passed. The newest source-claim recovery has
  not yet been verified end to end; these checks cannot validate every fact.
- Text Telegram requests now use the native OpenCode session API; media retains
  its existing CLI path. Native text submission and reply delivery were tested.
- Provider responses are buffered for completion checking before publication.
  This affects streaming text; progress updates remain separate.
- Feedback/session removal was exercised on diagnostic sessions. It removes
  application-owned session/derived memory, not arbitrary backups, Telegram's
  copies, or an undo of executed device actions.
- Model sampling recommendations were tested locally without changing
  production defaults. A parameter-only accuracy fix is not established.

Next: finish the direct-model investigation, trace the custom pipeline, and make
small generic fixes with focused tests and separate commits. Do not resume the
15-test suite or mutate home devices as part of this versioning task.
