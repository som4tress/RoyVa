#!/usr/bin/env bash
# Run the staged history-reliability test suite and write a machine-readable result.
# No network, no HA writes, no service restarts: fixtures only.
set -u
cd "$(dirname "$0")/.."
OUT=evidence/test-results.json
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

status=0
: >"$TMP/results.jsonl"

run_js() {
  local name="$1"; shift
  local log="$TMP/$name.log"
  if node "$@" >"$log" 2>&1; then rc=0; else rc=$?; status=1; fi
  python3 - "$name" "$rc" "$log" <<'PY' >>"$TMP/results.jsonl"
import json,sys
name,rc,path=sys.argv[1],int(sys.argv[2]),sys.argv[3]
text=open(path).read()
print(json.dumps({"suite":name,"runner":"node","exit":rc,"ok":rc==0,"output_tail":text[-1500:]}))
PY
  echo "== $name exit=$rc"
  tail -n 3 "$log"
}

run_py() {
  local name="$1"; shift
  local log="$TMP/$name.log"
  if python3 "$@" >"$log" 2>&1; then rc=0; else rc=$?; status=1; fi
  python3 - "$name" "$rc" "$log" <<'PY' >>"$TMP/results.jsonl"
import json,sys
name,rc,path=sys.argv[1],int(sys.argv[2]),sys.argv[3]
text=open(path).read()
print(json.dumps({"suite":name,"runner":"python3","exit":rc,"ok":rc==0,"output_tail":text[-1500:]}))
PY
  echo "== $name exit=$rc"
  tail -n 3 "$log"
}

run_js history_scope tests/test_history_scope.mjs
run_js history_contract tests/test_history_contract.mjs
run_js history_routing tests/test_history_routing.mjs
run_js request_classify tests/test_request_classify.mjs
run_js corrections tests/test_corrections.mjs
run_js learning_safety tests/test_learning_safety.mjs
run_js tool_integration tests/test_tool_integration.mjs
run_js plugin_pipeline tests/test_plugin_pipeline.mjs
run_py event_history_tool tests/test_event_history_tool.py

python3 - "$status" "$TMP/results.jsonl" "$OUT" <<'PY'
import json,sys,datetime
status,results_path,out_path=int(sys.argv[1]),sys.argv[2],sys.argv[3]
rows=[json.loads(line) for line in open(results_path) if line.strip()]
payload={
 "generated_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "suite":"history-reliability-20261101",
 "ok":status==0,
 "total_suites":len(rows),
 "passed":sum(1 for r in rows if r["ok"]),
 "failed":sum(1 for r in rows if not r["ok"]),
 "network_required":False,
 "ha_writes":False,
 "suites":rows,
 "note":"Fixture-based tests only. They validate staged logic, not deployed behavior.",
}
open(out_path,"w").write(json.dumps(payload,indent=2)+"\n")
print("results:",payload["passed"],"/",payload["total_suites"],"suites passed ->",out_path)
PY
rm -rf src/mcp/__pycache__
exit $status
