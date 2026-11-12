#!/usr/bin/env bash
# Run before restarting the stack: catches missing imports / typos that `node --check` and unit tests miss, then runs every test suite.
set -e
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$R"
[ -n "$LARES_NODE_BIN" ] && export PATH=$LARES_NODE_BIN:$PATH
echo "== undefined names (python)"; python3 tools/undefined_names.py $(git ls-files '*.py')
echo "== undefined names (js)";     node --expose-internals tools/undefined_names.js $(git ls-files '*.mjs' '*.js')
echo "== gateway tests";            (cd gateway && ./.venv/bin/python -m pytest -q > /tmp/royva-pytest.out 2>&1; s=$?; tail -2 /tmp/royva-pytest.out; exit $s)
echo "== bridge tests";             (cd bridge && node --test > /tmp/royva-nodetest.out 2>&1; s=$?; grep -E '^ℹ (tests|pass|fail)' /tmp/royva-nodetest.out; [ $s -eq 0 ] || grep -E '^not ok|✖' /tmp/royva-nodetest.out | head; exit $s)
echo "all checks passed"
