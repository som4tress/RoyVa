/**
 * Generic history-request scope parsing and resolution.
 *
 * Purpose: keep the user's requested device / event-type / local-day scope intact
 * while a historical question travels through routing, tools, subagents and the
 * final answer. Nothing here names a household device, room, brand or model.
 * Device selectors are resolved against a live entity/device catalog supplied by
 * the caller; this module only owns the grammar of history questions.
 */

export const SCHEMA_VERSION = 1;

const TZ_DEFAULT = 'America/Los_Angeles';

const STOP = new Set((
  'a an the please kindly me my you your i we our us it is are was were be been being ' +
  'what whats how hows could can would will tell say show give let know about of for in at to from ' +
  'with current currently status looking look doing do did does done have has had any all some ' +
  'there their they them this that these those and or but if then also just only very more most ' +
  'recordings recording recorded events event clips clip video videos footage times time timestamp ' +
  'timestamps yesterday today tonight tomorrow morning afternoon evening night day days date ' +
  'history historical log logs timeline happened happen occurred occur between since last past ' +
  'it its itself this that those them they their same previous ' +
  'camera cameras sensor sensors feed stream live view ' +
  'number count many much list total each per by during over ago hour hours minute minutes ' +
  'motion triggered trigger detected detect detection detect ding press pressed button ' +
  'on demand demand ready category type kinds kind kinds ' +
  'home assistant homeassistant ha smart house household ' +
  'share provide summarize summarise check look find get pull retrieve against please'
).split(/\s+/));

const EVENT_KIND_PATTERNS = [
  ['motion', /\bmotion|movement|motion[- ]triggered\b/i],
  ['ding', /\bding\b|\bdoorbell press(?:ed)?\b|\bbutton press(?:ed)?\b|\brang\b/i],
  ['on_demand', /\bon[- ]demand\b|\blive view\b|\bmanual(?:ly)? (?:view|record)/i],
  ['recording', /\brecording|\brecorded|\bclip|\bfootage|\bvideo\b/i],
  ['state_change', /\bstate change|\bturned (?:on|off)\b|\bswitched (?:on|off)\b|\bwater(?:ed|ing)?\b|\brun\b|\bcycle\b/i],
];

const LOCATION_SIGNAL = /\b(visit\w*|visited|location|locations|where|been|went|trip|away|home)\b/i;
const DAY_SIGNAL = /\b(yesterday|today|tonight|tomorrow|last night|this morning|this afternoon|this evening)\b/i;
const ROLLING_SIGNAL = /\b(?:last|past)\s+(\d{1,3})\s*(hours?|hrs?|days?)\b/i;
const DATE_SIGNAL = /\b(\d{4}-\d{2}-\d{2})\b/;
const HISTORY_SIGNAL = /\b(history|historical|recordings?|recorded|events?|clips?|footage|log|logs|timeline|happened|occurred|how many times|when did|did .{1,40} (?:run|water|trigger|detect|open|close))\b/i;

function norm(value) {
  return String(value ?? '').normalize('NFKC').toLowerCase().replace(/[’']/g, "'").replace(/[^a-z0-9]+/g, ' ').trim();
}

export function significantTokens(text) {
  return [...new Set(norm(text).split(' ').filter(t => t.length >= 2 && !STOP.has(t)))];
}

/** Date arithmetic on the requested timezone without relying on the host locale. */
export function localDay(nowMs, timeZone = TZ_DEFAULT) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date(nowMs)).filter(p => p.type !== 'literal').map(p => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function shiftLocalDay(isoDate, deltaDays) {
  const [y, m, d] = isoDate.split('-').map(Number);
  const base = new Date(Date.UTC(y, m - 1, d + deltaDays));
  return base.toISOString().slice(0, 10);
}

/** Resolve a requested window into explicit local-day boundaries. */
export function resolveWindow(text, { now = Date.now(), timeZone = TZ_DEFAULT } = {}) {
  const today = localDay(now, timeZone);
  const rolling = String(text).match(ROLLING_SIGNAL);
  if (rolling) {
    const n = Number(rolling[1]);
    if (n >= 1 && n <= 168) {
      const unit = /^d/.test(rolling[2]) ? 24 : 1;
      return { kind: 'rolling', hours: n * unit, timeZone, asOf: new Date(now).toISOString() };
    }
  }
  const explicit = String(text).match(DATE_SIGNAL);
  if (explicit) {
    const date = explicit[1];
    return { kind: 'local_day', date, timeZone, from: `${date}T00:00:00`, to: `${shiftLocalDay(date, 1)}T00:00:00`, label: date };
  }
  if (/\bday before yesterday\b/i.test(text)) {
    const date = shiftLocalDay(today, -2);
    return { kind: 'local_day', date, timeZone, from: `${date}T00:00:00`, to: `${shiftLocalDay(date, 1)}T00:00:00`, label: date };
  }
  if (/\byesterday\b|\blast night\b/i.test(text)) {
    const date = shiftLocalDay(today, -1);
    return { kind: 'local_day', date, timeZone, from: `${date}T00:00:00`, to: `${shiftLocalDay(date, 1)}T00:00:00`, label: 'yesterday' };
  }
  if (/\btonight\b/i.test(text)) {
    return { kind: 'local_day', date: today, timeZone, from: `${today}T00:00:00`, to: `${shiftLocalDay(today, 1)}T00:00:00`, label: 'today' };
  }
  if (/\btoday\b|\bthis (?:morning|afternoon|evening)\b/i.test(text)) {
    return { kind: 'local_day', date: today, timeZone, from: `${today}T00:00:00`, to: `${shiftLocalDay(today, 1)}T00:00:00`, label: 'today' };
  }
  if (/\btomorrow\b/i.test(text)) {
    const date = shiftLocalDay(today, 1);
    return { kind: 'local_day', date, timeZone, from: `${date}T00:00:00`, to: `${shiftLocalDay(date, 1)}T00:00:00`, label: 'tomorrow', future: true };
  }
  return null;
}

export function detectEventKinds(text) {
  const kinds = [];
  for (const [name, pattern] of EVENT_KIND_PATTERNS) if (pattern.test(text)) kinds.push(name);
  // "recording(s)" alone describes the object being counted; it does not narrow the
  // trigger type. Only keep it when no concrete trigger type was requested.
  if (kinds.includes('recording') && kinds.length > 1) kinds.splice(kinds.indexOf('recording'), 1);
  return kinds;
}

/**
 * True only for recorded person visits/locations. This keeps device/event/recording
 * history out of the person-location tool path (an earlier conflation caused the
 * model to call get_visited_locations for camera events).
 */
export function isPersonLocationHistory(text) {
  const s = String(text);
  if (/\b(stock|news|flight|ticket|vacation|holiday)\b/i.test(s)) return false;
  if (/\b(camera|cameras|doorbell|door bell|recording|recordings|clip|footage|video|sensor|device|devices|switch|switches|camera events?)\b/i.test(s)) return false;
  return LOCATION_SIGNAL.test(s) && /\b(today|yesterday|visited|visits|history|logged|been|went|locations?)\b/i.test(s);
}

/** True when the text asks for device/sensor/event history (not person visits). */
export function isEntityHistory(text) {
  const s = String(text);
  if (isPersonLocationHistory(s)) return false;
  if (!HISTORY_SIGNAL.test(s)) return false;
  if (!DAY_SIGNAL.test(s) && !ROLLING_SIGNAL.test(s) && !DATE_SIGNAL.test(s) && !/\bhistory|historical|timeline|log|recordings|recorded\b/i.test(s)) return false;
  return true;
}

/**
 * Parse a device/event history request into an explicit scope contract.
 * Returns null when the text is not an entity-history request.
 */
export function parseHistoryRequest(text, { now = Date.now(), timeZone = TZ_DEFAULT } = {}) {
  const raw = String(text ?? '').trim();
  if (!raw || !isEntityHistory(raw)) return null;
  const window = resolveWindow(raw, { now, timeZone });
  const eventKinds = detectEventKinds(raw);
  // Explicit current constraints ("not the driveway", "except the backyard") must
  // beat any remembered example or broader default scope.
  const negative = raw.match(/[.;,]?\s*(?:but\s+)?(?:not|except|excluding|other than|apart from|without)\s+(.+)$/i);
  const positiveText = negative ? raw.slice(0, negative.index) : raw;
  const selectorText = stripScaffolding(positiveText);
  const excludedSelectorText = negative ? stripScaffolding(negative[1]) : '';
  const excludedTokens = excludedSelectorText ? significantTokens(excludedSelectorText) : [];

  const plurality = /\b(all|every|each|both)\b/i.test(raw) ? 'plural'
    : /\bthe\b[^.]{0,80}\b(?:camera|doorbell|sensor|device|switch|valve|light)\b/i.test(raw) && !/\b(cameras|doorbells|sensors|devices|switches|valves|lights)\b/i.test(raw) ? 'singular'
      : 'unspecified';

  const limitations = [];
  if (!window) limitations.push('No local-day or rolling window could be resolved; the requested period must be stated before any count is reported.');
  if (window?.future) limitations.push('The requested window is in the future; only an empty result is possible.');

  return {
    version: SCHEMA_VERSION,
    kind: 'entity_history',
    requiresGeneralTools: true,
    capability: 'recorder_entity_history',
    raw,
    window,
    eventKinds,
    selectorText,
    selectorTokens: significantTokens(selectorText),
    excludedSelectorText: excludedSelectorText || null,
    excludedTokens,
    plurality,
    asksForTimes: /\b(times?|timestamps?|when|list|each|chronolog)/i.test(raw),
    followupReference: /\b(?:it|its|it's|this|that|those|them|they|same)\b/i.test(raw),
    asksForCount: /\b(how many|count|number|total)\b/i.test(raw),
    requested: {
      scopeText: selectorText || null,
      excludedText: excludedSelectorText || null,
      eventKinds,
      window,
      plurality,
    },
    limitations,
  };
}

/** Remove question scaffolding and time/event vocabulary, leaving the device words. */
export function stripScaffolding(text) {
  return norm(String(text)
    .replace(ROLLING_SIGNAL, ' ')
    .replace(DATE_SIGNAL, ' ')
    .replace(/\b(yesterday|today|tonight|tomorrow|last night|this morning|this afternoon|this evening|day before yesterday)\b/gi, ' ')
    .replace(/\b(how many|how much|what|which|when|did|does|do|were there|was there|are there|is there|show me|show|list|tell me|give me|share|provide|summari[sz]e|check|find|pull|retrieve|count|total)\b/gi, ' ')
    .replace(/\b(times?|timestamps?|chronological(?:ly)?|along with|along|their|there)\b/gi, ' '));
}

/**
 * Resolve selector words against a catalog of entities/devices.
 * catalog items: {entity_id, name, domain, device_name?, aliases?: string[]}
 * Returns matched items plus explicit resolution problems. No match is reported as
 * "unresolved", never as proof that the capability or entity does not exist.
 */
export function resolveHistoryScope(plan, catalog = []) {
  if (!plan) return { matched: [], problems: ['no_history_plan'] };
  const items = (catalog || []).filter(item => item && typeof item.entity_id === 'string');
  const queryTokens = plan.selectorTokens;
  const problems = [];

  const scored = items.map(item => {
    const haystack = norm([item.name, item.entity_id, item.device_name, ...(item.aliases || [])].filter(Boolean).join(' '));
    const hayTokens = new Set(haystack.split(' '));
    const matched = queryTokens.filter(t => hayTokens.has(t) || (t.length >= 4 && [...hayTokens].some(h => h.startsWith(t))));
    const score = queryTokens.length ? matched.length / queryTokens.length : 0;
    return { item, score, matched };
  });

  // Every selector token must match one entity; a partially matching device must
  // never be silently substituted for the device the user named.
  let matched = scored.filter(x => x.score >= 0.999).map(x => x.item);

  matched = dedupeByIdentity(matched);
  if (plan.excludedTokens?.length) {
    matched = matched.filter(item => {
      const haystack = new Set(norm([item.name, item.entity_id, item.device_name, ...(item.aliases || [])].filter(Boolean).join(' ')).split(' '));
      const isExcluded = plan.excludedTokens.every(t => haystack.has(t));
      return !isExcluded;
    });
  }
  matched = preferOneSourcePerDevice(matched);

  if (!queryTokens.length) {
    if (plan.followupReference) problems.push('pending_reference: the request refers to an earlier subject; resolve only from the immediately preceding exchange, never from procedural memory, and ask if that subject is not a concrete resolved device.');
    else problems.push('unresolved_scope: the request names no device or source; ask which device/source is meant.');
  }
  else if (!matched.length) problems.push('unresolved_scope: no catalog entity matched the requested words. This is not proof that the device or capability is absent; search the domain catalog and device registry before concluding anything.');

  const requestedPlural = plan.plurality === 'plural';
  if (matched.length > 1 && plan.plurality === 'singular') problems.push('scope_broadened: the request names one device but resolution matched ' + matched.length + ' (' + matched.map(m => m.name || m.entity_id).join(', ') + '). Do not merge them; ask which one, or report per-device results only after the user confirms the set.');

  // Event-kind narrowing: an entity must expose the requested trigger attribute when the
  // request names a concrete trigger type. Missing attributes are exclusions, not zero.
  const requiresCategory = plan.eventKinds.some(k => ['motion', 'ding', 'on_demand'].includes(k));
  const usable = [], excluded = [];
  for (const item of matched) {
    if (requiresCategory && !itemHasEventAttributes(item)) excluded.push({ ...identity(item), reason: 'no_event_attributes' });
    else usable.push(item);
  }
  if (matched.length && !usable.length) problems.push('unresolved_scope: matched entities expose no event/category attributes; this source cannot answer a trigger-type count. Report the source limitation, not a zero count.');

  return { matched: usable, excluded, problems, requestedCount: queryTokens.length, plural: requestedPlural };
}

function itemHasEventAttributes(item) {
  if (item.has_event_attributes === true) return true;
  if (item.has_event_attributes === false) return false;
  // Unknown metadata must not silently drop an entity; the recorder tool checks the
  // returned rows and reports "no event attributes in rows" instead.
  return true;
}

export function identity(item) {
  return { entity_id: item.entity_id, name: item.name || item.entity_id, domain: item.domain || String(item.entity_id).split('.')[0] };
}

function dedupeByIdentity(items) {
  const seen = new Map();
  for (const item of items) seen.set(item.entity_id, item);
  return [...seen.values()];
}

const SOURCE_RANK = ['sensor', 'binary_sensor', 'event', 'switch', 'valve', 'input_boolean', 'light', 'climate', 'fan', 'cover', 'lock', 'media_player', 'camera'];

/**
 * Several entities can describe the same device (camera view + last-activity
 * timestamp + event entity). Counting all of them double counts. Keep one source
 * per device, preferring an explicitly event-attribute source, then a state-history
 * domain, and only then a live-view/media entity.
 */
function preferOneSourcePerDevice(items) {
  const groups = new Map();
  for (const item of items) {
    const key = item.device_id || item.device_name || item.name || item.entity_id;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  const rank = item => (item.event_attributes === true ? -1 : SOURCE_RANK.indexOf(item.domain || String(item.entity_id).split('.')[0]));
  return [...groups.values()].map(group => group.slice().sort((a, b) => rank(a) - rank(b) || String(a.entity_id).localeCompare(String(b.entity_id)))[0]);
}

/** Verify a resolved set against the original request. Returns [] when preserved. */
export function scopePreserved(plan, resolution) {
  const errors = [];
  if (!plan) return ['no_history_plan'];
  for (const problem of resolution.problems || []) {
    const code = String(problem).split(':')[0].trim();
    if (code) errors.push(code);
  }
  if (!resolution.matched?.length) errors.push('no_resolved_entities');
  if (plan.plurality === 'singular' && (resolution.matched?.length || 0) > 1) {
    errors.push('mixed_entities_for_singular_request');
  }
  return [...new Set(errors)];
}
