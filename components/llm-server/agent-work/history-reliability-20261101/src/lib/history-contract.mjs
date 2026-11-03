/**
 * History evidence contract: ties a claimed count / timeline to the rows that
 * actually support it, and labels what kind of evidence it is.
 *
 * The observed failures were not arithmetic mistakes; they were provenance
 * failures: recorder "last activity" metadata presented as the provider's list of
 * recordings, several cameras merged for a singular request, and counts with no
 * reproducible row set. This module makes those claims mechanically checkable.
 */

export const SCHEMA_VERSION = 1;

export const EVIDENCE = Object.freeze({
  AUTHORITATIVE_PROVIDER: 'authoritative_provider',
  OBSERVED_METADATA: 'observed_metadata',
  PROXY_SIGNAL: 'proxy_signal',
});

export const EVIDENCE_LABEL = Object.freeze({
  [EVIDENCE.AUTHORITATIVE_PROVIDER]: 'provider-authoritative list',
  [EVIDENCE.OBSERVED_METADATA]: 'HA-observed metadata (recorder)',
  [EVIDENCE.PROXY_SIGNAL]: 'polling/proxy signal (not an event list)',
});

const EVENT_NOUN = {
  motion: 'motion events',
  ding: 'doorbell/button presses',
  on_demand: 'on-demand/live-view events',
  recording: 'recordings',
  state_change: 'state changes',
};

export function eventNoun(kinds) {
  const list = (kinds && kinds.length ? kinds : ['recording']).map(k => EVENT_NOUN[k] || k);
  return list.join(' / ');
}

const isoLocal = (value, timeZone) => {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(date).filter(p => p.type !== 'literal').map(p => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
};

/** Normalize rows returned by an entity-history reader into contract rows. */
export function normalizeRows(rows = [], { timeZone = 'America/Los_Angeles' } = {}) {
  return rows.map(row => {
    const stamp = row.created_at || row.timestamp || row.last_changed || row.state;
    return {
      entity_id: row.entity_id,
      device: row.name || row.device || row.entity_id,
      at_utc: stamp ? new Date(stamp).toISOString() : null,
      at_local: isoLocal(stamp, timeZone),
      state: row.state ?? null,
      category: row.category ?? null,
      recording_status: row.recording_status ?? null,
    };
  });
}

/**
 * Build the contract from the tool result. `source` must describe the concrete
 * origin; `evidenceClass` must be chosen deliberately, never defaulted by callers
 * who want a stronger claim.
 */
export function buildHistoryContract({
  plan,
  resolution,
  rows = [],
  excluded = [],
  source = 'Home Assistant recorder',
  evidenceClass = EVIDENCE.OBSERVED_METADATA,
  artifact = null,
  timeZone = 'America/Los_Angeles',
  completeness = {},
  sourceVersions = {},
  selection = {},
} = {}) {
  if (!Object.values(EVIDENCE).includes(evidenceClass)) throw new Error('Unknown evidence class: ' + evidenceClass);
  if (!plan) throw new Error('A history contract requires a parsed request plan.');
  const normalized = normalizeRows(rows, { timeZone });
  const byEntity = new Map();
  for (const row of normalized) {
    const id = row.entity_id || 'unknown';
    if (!byEntity.has(id)) byEntity.set(id, { entity_id: id, device: row.device, rows: [], categories: {} });
    const entry = byEntity.get(id);
    entry.rows.push(row);
    const category = row.category || '(none)';
    entry.categories[category] = (entry.categories[category] || 0) + 1;
  }
  const counts = [...byEntity.values()].map(entry => ({
    entity_id: entry.entity_id,
    device: entry.device,
    count: entry.rows.length,
    categories: entry.categories,
    first_local: entry.rows[0]?.at_local || null,
    last_local: entry.rows.at(-1)?.at_local || null,
  }));
  const exclusionCounts = {};
  for (const item of excluded || []) exclusionCounts[item.reason || 'excluded'] = (exclusionCounts[item.reason || 'excluded'] || 0) + 1;

  return {
    version: SCHEMA_VERSION,
    kind: 'history_contract',
    requested: {
      raw: plan.raw,
      scope_text: plan.requested?.scopeText || null,
      event_kinds: plan.eventKinds || [],
      plurality: plan.plurality,
      window: plan.window,
      asks_for_times: !!plan.asksForTimes,
      asks_for_count: !!plan.asksForCount,
    },
    resolved: {
      entities: (resolution?.matched || []).map(m => ({ entity_id: m.entity_id, name: m.name || m.entity_id, domain: m.domain || String(m.entity_id).split('.')[0] })),
      problems: resolution?.problems || [],
    },
    source,
    evidence_class: evidenceClass,
    evidence_label: EVIDENCE_LABEL[evidenceClass],
    filter_semantics: {
      trigger_types: plan.eventKinds || [],
      attribute_filters: selection.attribute_filters || {},
      state_filter: selection.state_filter || null,
      dedupe_key: selection.dedupe_by || 'created_at',
      initial_state_excluded: selection.initial_state_excluded !== false,
      event_time_basis: selection.event_time_basis || 'created_at when present, else recorder last_changed',
      source_entities: (resolution?.matched || []).map(m => m.entity_id),
    },
    unique_key_definition: 'One row per (entity_id, dedupe key); for recording metadata the dedupe key is the recording start attribute (created_at).',
    time_zone: timeZone,
    window: plan.window,
    rows: normalized,
    counts_by_entity: counts,
    total: normalized.length,
    excluded,
    exclusion_counts: exclusionCounts,
    artifact,
    completeness: {
      complete_within_source: completeness.complete_within_source !== false,
      provider_complete: evidenceClass === EVIDENCE.AUTHORITATIVE_PROVIDER ? completeness.provider_complete !== false : false,
      notes: completeness.notes || (evidenceClass === EVIDENCE.OBSERVED_METADATA
        ? 'Counts reflect rows HA recorded/polled in the requested window. Events the integration never observed are not visible here.'
        : []),
    },
    source_versions: {
      schema: SCHEMA_VERSION,
      ...sourceVersions,
    },
    read_only: true,
    generated_at: new Date().toISOString(),
  };
}

const QUALIFIER = /(HA[- ]observed|observed metadata|recorder|poll(?:ing|ed)?|sensor metadata|last[- ]activity|not (?:the )?(?:provider|Ring)(?:'s)? (?:own )?(?:list|clip list)|lower bound|floor|not authoritative)/i;
const ABSOLUTE = /(\bnone\b|\bno (?:recordings?|events?|clips?|motion|activity)\b|\bzero\b|\bnever\b|\bimpossible\b|\bcannot\b|\bcan't\b)/i;

/**
 * Validate a claim (what the model/renderer is about to say) against the contract.
 * claim: {total?, counts_by_entity?, text, says_authoritative?, window_stated?}
 * Returns {ok, errors, warnings}. Errors mean the answer must not be sent as-is.
 */
export function validateHistoryClaim(contract, claim = {}) {
  const errors = [], warnings = [];
  if (!contract || contract.kind !== 'history_contract') return { ok: false, errors: ['missing_contract'], warnings };
  const text = String(claim.text || '');
  const requestedIds = new Set((contract.resolved?.entities || []).map(e => e.entity_id));
  const claimedCount = claim.total ?? contract.total;

  if (claim.total !== undefined && claim.total !== contract.total) errors.push(`count_mismatch: claimed ${claim.total}, rows support ${contract.total}`);
  if (claim.counts_by_entity) {
    const sum = Object.values(claim.counts_by_entity).reduce((n, v) => n + Number(v || 0), 0);
    if (sum !== contract.total) errors.push(`per_entity_sum_mismatch: per-device counts total ${sum}, rows support ${contract.total}`);
    for (const entityID of Object.keys(claim.counts_by_entity)) {
      if (!requestedIds.has(entityID)) errors.push(`unrequested_entity: ${entityID} is outside the resolved request scope`);
    }
  }
  if (contract.resolved?.problems?.length) errors.push('scope_unresolved: ' + contract.resolved.problems.join('; '));

  // Mixed devices are allowed only when the answer names every resolved device.
  if ((contract.resolved?.entities?.length || 0) > 1) {
    const unnamed = contract.resolved.entities.filter(e => !text.toLowerCase().includes(String(e.name).toLowerCase()) && !text.includes(e.entity_id));
    if (unnamed.length) errors.push('mixed_devices_unstated: answer merges ' + unnamed.length + ' device(s) without naming them (' + unnamed.map(e => e.name).join(', ') + ')');
  }

  if (contract.requested?.plurality === 'singular' && (contract.resolved?.entities?.length || 0) > 1) {
    errors.push('scope_broadened_for_singular_request');
  }

  if (!contract.window) errors.push('window_missing');
  if (!claim.window_stated && contract.window && !new RegExp(contract.window.date || '____').test(text) && !/\byesterday\b|\btoday\b|\blast\s+\d+\s*(?:hours?|days?)\b/i.test(text)) {
    warnings.push('window_not_stated_in_answer');
  }

  if (contract.evidence_class !== EVIDENCE.AUTHORITATIVE_PROVIDER) {
    if (!claim.qualified && QUALIFIER.test(text) === false && contract.total > 0) {
      errors.push('provenance_unstated: observed metadata must be labelled as such, and must not be presented as the provider list');
    }
    if (claim.says_authoritative) errors.push('false_authority: observed metadata cannot be described as the authoritative or complete provider list');
  }

  // "No X" is a strong claim. It is allowed only when the source covers the scope,
  // the device set was resolved, and the absence is stated within that source.
  if (ABSOLUTE.test(text) && contract.total === 0) {
    if (contract.evidence_class !== EVIDENCE.AUTHORITATIVE_PROVIDER) {
      if (!/within (?:the )?(?:HA|recorder|observed|that)/i.test(text)) errors.push('unqualified_absence: a zero result from observed metadata is not proof that no event happened; scope the absence to the source');
    }
  }
  if (ABSOLUTE.test(text) && contract.total > 0 && !claim.qualified && /\bnone\b|\bno (?:recordings?|events?|clips?)\b/i.test(text)) {
    errors.push('contradictory_absence: text claims none while rows exist');
  }

  if (contract.exclusion_counts && Object.keys(contract.exclusion_counts).length && !claim.exclusions_stated) {
    warnings.push('excluded_rows_not_stated: ' + JSON.stringify(contract.exclusion_counts));
  }

  if (contract.requested?.asks_for_times && contract.total > 0 && !contract.artifact) {
    warnings.push('no_artifact_for_timeline: a per-event list should be saved so the count is reproducible');
  }

  if (!contract.read_only) errors.push('contract_not_read_only');
  if (contract.total > 0 && !contract.unique_key_definition) errors.push('unique_key_undefined');
  if (!contract.filter_semantics || !Object.keys(contract.filter_semantics).length) errors.push('filter_semantics_missing');
  if (claim.claims_complete_provider && contract.evidence_class !== EVIDENCE.AUTHORITATIVE_PROVIDER) errors.push('false_completeness');

  return { ok: errors.length === 0, errors, warnings };
}

/**
 * Deterministic renderer. Producing the answer from the contract removes the
 * opportunity to relabel a proxy count or drop the requested scope.
 */
export function renderHistoryAnswer(contract, { maxRows = 40, scopeStyle = 'table' } = {}) {
  const window = contract.window || {};
  const scopeNames = (contract.resolved?.entities || []).map(e => e.name);
  const windowLabel = window.kind === 'rolling'
    ? `the last ${window.hours} hours`
    : (window.label && window.label !== window.date ? `${window.label} (${window.date})` : window.date) || 'the requested period';
  const noun = eventNoun(contract.requested?.event_kinds);
  const evidence = contract.evidence_label;
  const lines = [];

  lines.push(`**${contract.total}** ${noun} in ${windowLabel}${window.kind === 'local_day' && window.timeZone ? ` (${window.timeZone})` : ''}`);
  if (scopeNames.length) lines.push(`Source scope: ${scopeNames.join(', ')} — evidence: ${evidence}, from ${contract.source}.`);
  else lines.push(`Evidence: ${evidence}, from ${contract.source}.`);

  if ((contract.counts_by_entity || []).length > 1) {
    lines.push('');
    lines.push('| Device | Count | First (local) | Last (local) |');
    lines.push('| --- | --- | --- | --- |');
    for (const row of contract.counts_by_entity) {
      lines.push(`| ${row.device} | ${row.count} | ${row.first_local || '—'} | ${row.last_local || '—'} |`);
    }
  } else if (contract.total && contract.counts_by_entity?.[0]) {
    const only = contract.counts_by_entity[0];
    lines.push(`First ${only.first_local}, last ${only.last_local} (local).`);
  }

  if (contract.exclusion_counts && Object.keys(contract.exclusion_counts).length) {
    lines.push('');
    lines.push('Excluded: ' + Object.entries(contract.exclusion_counts).map(([reason, n]) => `${n} ${reason.replace(/_/g, ' ')}`).join(', ') + '.');
  }

  const times = contract.rows.slice(0, maxRows).map(r => r.at_local).filter(Boolean);
  if (times.length && contract.total <= maxRows) {
    lines.push('');
    lines.push('Local times: ' + times.join(', '));
  } else if (times.length) {
    lines.push('');
    lines.push(`Local times for the first ${times.length} rows: ${times.join(', ')}` + (contract.artifact ? `; full list: \`${contract.artifact}\`.` : '.'));
  }

  lines.push('');
  lines.push(`Limitation: ${typeof contract.completeness?.notes === 'string' ? contract.completeness.notes : 'Events outside this source are not visible.'}`);

  return lines.join('\n');
}
