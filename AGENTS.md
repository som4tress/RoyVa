# Required change workflow

This repository versions Royva's deployed custom code, configuration templates,
service definitions, tests, and the pinned upstream OpenCode source.

Before changing deployed files, run `python3 tools/capture.py --check` and inspect
any existing drift. Preserve other agents' work separately; never
overwrite it or assume it is part of your own change.

Commit only when the user explicitly requests a commit for the current change.
Do not commit test results or benchmark reports unless specifically authorized.
Run focused relevant checks and capture deployed sources for review. When a
commit is authorized, inspect `git diff` and use a descriptive commit message
limited to that change. Keep test results in the conversation or private files
unless the user asks otherwise. A commit is a checkpoint, not a claim that the
code is correct. Do not claim untested fixes.

Deployed paths remain in their original locations. The repository mirrors them;
the capture/check commands detect drift, but do not deploy or automatically
commit. Never restore redacted snapshots over live credential configuration.

Do not commit credentials, environment files, sessions, conversation payloads,
runtime learning data, model weights, dependencies, or generated builds. Do not
publish or push without a user instruction. Record upstream source revisions
and installed binary hashes; updating source does not update the running binary.
