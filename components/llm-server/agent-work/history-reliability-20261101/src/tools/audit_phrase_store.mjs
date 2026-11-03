#!/usr/bin/env node
/**
 * Read-only audit of the learned-phrase store.
 *
 * Conflicting rows (same wording learned as different kinds) are the mechanism that
 * routed a camera-event question to person-location history. The staged phrases.js
 * refuses ambiguous exact matches, so this audit only reports what exists; it never
 * edits the store.
 *
 * Usage: node src/tools/audit_phrase_store.mjs [path-to-learned-phrases.json]
 */
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const path = process.argv[2] || join(homedir(), '.local/share/opencode/ha-router/learned-phrases.json');
let data;
try {
  data = JSON.parse(readFileSync(path, 'utf8'));
} catch (error) {
  console.error('Could not read phrase store:', error.message);
  process.exit(2);
}
const rows = Array.isArray(data.phrases) ? data.phrases : [];
const groups = new Map();
for (let index = 0; index < rows.length; index++) {
  const row = rows[index];
  const key = (row.tokens || []).join(' ');
  if (!key) continue;
  if (!groups.has(key)) groups.set(key, []);
  groups.get(key).push({ index, kind: row.kind, example: row.example, count: row.count || 1, ambiguous: !!row.ambiguous });
}
const conflicts = [...groups.entries()].filter(([, list]) => new Set(list.map(r => r.kind)).size > 1);
console.log(JSON.stringify({
  path,
  total_phrases: rows.length,
  conflicting_token_shapes: conflicts.length,
  conflicts: conflicts.map(([tokens, list]) => ({
    tokens,
    kinds: [...new Set(list.map(r => r.kind))],
    examples: [...new Set(list.map(r => r.example))].filter(Boolean).slice(0, 3),
    recommendation: 'quarantine: deterministic classification must decide this wording',
  })),
  read_only: true,
}, null, 2));
process.exit(conflicts.length ? 1 : 0);
