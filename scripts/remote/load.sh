#!/usr/bin/env bash
. "$(dirname "${BASH_SOURCE[0]}")/_box.sh"
# Samples the 3090 box for about 70 s and saves the raw output here, labelled, so runs can be compared.
# Run:  ! bash ~/RoyVa/scripts/remote/load.sh idle      (or: homework, class, ...)
L="${1:-run}"
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
O="$D/../../runtime/load"; mkdir -p "$O"
F="$O/$(date +%Y%m%d-%H%M)-$L.txt"
ssh ${BOX_SSH} "bash -s 60" < "$D/sample-load.sh" | tee "$F" | tail -25
python3 "$D/summarize-load.py" "$O"/*.txt
