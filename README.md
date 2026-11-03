# Jarvis runtime baseline

This local repository records the current EVO deployment. It is an **as-is
baseline with known bugs**, not a certified working release.

Included:

- OpenCode configuration, agents, instructions, plugins, MCP adapters, Telegram
  bridge and supporting scripts.
- Agent learning/feedback code, smart router, Shellular source including the
  deployed client modifications, inference launch/configuration code, startup
  scripts, test and development source, and user service/cron definitions.
- Upstream OpenCode source as a Git submodule pinned to **v2.2.5**.
- A source-to-deployment manifest and installed executable hashes.

Credentials, conversation/session data, runtime learning records, model weights,
dependencies, generated builds and archived backup copies are excluded. Existing
Git repositories retain their original histories; the baseline mirrors their
source, not their `.git` directories. Unrelated VideoClassification edits in the
parent Projects repository are untouched.

## Workflow

```sh
cd /home/somdutta/Documents/Codex/jarvis-runtime
python3 tools/capture.py --check
# Inspect existing drift; make one logical change and run focused checks.
python3 tools/capture.py
git diff --stat
git diff
git add components inventory docs tools AGENTS.md README.md .gitignore
git commit -m "fix: describe the behavior changed" -m "Validation and remaining limits."
```

The capture command reads deployed code and writes repository mirrors. It does
**not** modify production or restart services. `--check` exits nonzero if sources
have drifted. There is no automatic commit: the agent making a change must review
and commit it. The local pre-commit hook checks staged files for known credential
values and common token formats; it is an aid, not a guarantee of no secrets.

Mirrors retain deployment-specific paths. Redacted files are identified in
`inventory/sources.json`; do not deploy redacted snapshots over live configuration.
Restore individual changes deliberately, preserving private environment files.

Initialize pinned upstream code after cloning:

```sh
git submodule update --init --recursive
git config core.hooksPath .githooks
```

The upstream checkout records a matching version tag, not proof of a reproducible
binary build. Compare the installed binary hash in `inventory/deployment.json`
before attributing behavior to a particular build. Updating the source submodule
does not replace the running executable.
