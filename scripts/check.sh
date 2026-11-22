#!/usr/bin/env bash
# Run before restarting the stack: catches missing imports / typos that `node --check` and unit tests miss, then runs every test suite.
set -e
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$R"
eval "$(python3 "$R/scripts/lares_config.py")" || exit 1       # node location comes from lares.toml, not from the caller
[ -n "$LARES_NODE_BIN" ] && export PATH=$LARES_NODE_BIN:$PATH
echo "== undefined names (python)"; python3 tools/undefined_names.py $(git ls-files '*.py')
echo "== undefined names (js)";     node --expose-internals tools/undefined_names.js $(git ls-files '*.mjs' '*.js')
echo "== doors to the 3090 box";    python3 tools/check_3090_doors.py
echo "== gateway tests";            (cd gateway && ./.venv/bin/python -m pytest -q > /tmp/royva-pytest.out 2>&1; s=$?; tail -2 /tmp/royva-pytest.out; exit $s)
echo "== bridge tests";             (cd bridge && node --test > /tmp/royva-nodetest.out 2>&1; s=$?; grep -E '^ℹ (tests|pass|fail)' /tmp/royva-nodetest.out; [ $s -eq 0 ] || grep -E '^not ok|✖' /tmp/royva-nodetest.out | head; exit $s)
echo "== document reader tests"; gateway/.venv/bin/python -m unittest mcp.docs.test_docs 2>&1 | tail -3; [ "${PIPESTATUS[0]}" -eq 0 ] || { echo "document reader tests FAILED"; exit 1; }
echo "== img_video wrapper tests"; python3 -m unittest mcp.img_video.test_server 2>&1 | tail -3; [ "${PIPESTATUS[0]}" -eq 0 ] || { echo "img_video wrapper tests FAILED"; exit 1; }
echo "== img_video agent tests"; (cd agents/img_video && python3 -m unittest discover -s tests > /tmp/royva-agent-tests.out 2>&1; s=$?; tail -3 /tmp/royva-agent-tests.out; exit $s) || { echo "img_video agent tests FAILED"; exit 1; }
echo "all checks passed"
