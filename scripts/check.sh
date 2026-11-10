#!/usr/bin/env bash
# Run before restarting the stack: catches missing imports / typos that `node --check` and unit tests miss, then runs every test suite.
set -e
R=/home/somdutta/RoyVa; cd "$R"
export PATH=/home/somdutta/.nvm/versions/node/v24.22.1/bin:$PATH
echo "== undefined names (python)"; python3 tools/undefined_names.py $(git ls-files '*.py')
echo "== undefined names (js)";     node --expose-internals tools/undefined_names.js $(git ls-files '*.mjs' '*.js')
echo "== gateway tests";            (cd gateway && ./.venv/bin/python -m pytest -q 2>&1 | tail -2)
echo "== bridge tests";             (cd bridge && node --test 2>&1 | grep -E '^ℹ (tests|pass|fail)')
echo "all checks passed"
