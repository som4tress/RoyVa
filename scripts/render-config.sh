#!/usr/bin/env bash
# Renders config/opencode.json (gitignored, machine-specific absolute paths) from config/opencode.template.json by replacing @HOME@ with $HOME.
# Run again after editing the template:  bash scripts/render-config.sh
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sed "s#@HOME@#${HOME}#g" "$R/config/opencode.template.json" > "$R/config/opencode.json.new" && mv "$R/config/opencode.json.new" "$R/config/opencode.json"
