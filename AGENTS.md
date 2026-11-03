# Required change workflow

This repository versions Royva's deployed custom code, configuration templates,
service definitions, tests, and the pinned upstream OpenCode source.

Before changing deployed files, run `python3 tools/capture.py --check` and inspect
any existing drift. Preserve and commit other agents' work separately; never
overwrite it or assume it is part of your own change.

Every logical code or configuration change requires a descriptive Git commit.
Run focused relevant checks, run `python3 tools/capture.py`, review `git diff`,
then commit with a message describing the behavior changed and why. Record tests
and remaining failures in the commit body or docs. A commit is a checkpoint,
not a claim that the code is correct. Do not claim untested fixes.

Deployed paths remain in their original locations. The repository mirrors them;
the capture/check commands detect drift, but do not deploy or automatically
commit. Never restore redacted snapshots over live credential configuration.

Do not commit credentials, environment files, sessions, conversation payloads,
runtime learning data, model weights, dependencies, or generated builds. Do not
publish or push without a user instruction. Record upstream source revisions
and installed binary hashes; updating source does not update the running binary.
