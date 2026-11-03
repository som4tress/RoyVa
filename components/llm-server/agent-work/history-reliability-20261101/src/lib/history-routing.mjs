/**
 * Routing decisions for historical requests, kept as pure functions so they can be
 * tested without mounting the OpenCode plugin runtime.
 *
 * Two different meanings of "history" used to share one route:
 *   - person visit history  -> narrow recorded zone intervals (ha-history tool)
 *   - device/event history  -> general read-only investigation (recorder API,
 *                              filesystem, integration metadata)
 * Conflating them made capable models announce "no tool can do this" while a
 * shell/API read was both allowed and sufficient.
 */
import { isPersonLocationHistory, parseHistoryRequest, resolveHistoryScope, scopePreserved } from './history-scope.mjs';

export const WRITE_TOOL = /HassTurn(?:On|Off)$|HassLightSet$|HassFanSetSpeed$|HassClimateSetTemperature$|HassMediaPlayerMute$|HassMediaPlayerUnmute$|HassMediaPause$|HassMediaUnpause$|HassMediaNext$|HassMediaPrevious$|HassSetVolume|HassCancelAllTimers$|HassBroadcast$|play_media$|HassMediaPlayer/;

export function isWriteTool(name) {
  return WRITE_TOOL.test(String(name || ''));
}

/**
 * Decide how a historical request must be handled.
 * Returns null when the text is not historical.
 */
export function decideHistoryRoute(text, {
  now = Date.now(),
  timeZone = 'America/Los_Angeles',
  catalog = [],
  generalLocalMs = 30000,
  cloudMs = 120000,
  policyVersion = 1,
} = {}) {
  const raw = String(text ?? '').trim();
  if (!raw) return null;

  if (isPersonLocationHistory(raw)) {
    return {
      kind: 'history',
      history_class: 'person_location',
      requires_general_tools: false,
      allowed_tool_pattern: /^ha[-_]history_/,
      local_budget_ms: generalLocalMs,
      cloud_budget_ms: cloudMs,
      cloud_budget_is_fresh: true,
      preserve_completed_results: true,
      allow_writes: false,
      reason: 'Recorded person visit history uses the bounded zone-history tool.',
    };
  }

  const plan = parseHistoryRequest(raw, { now, timeZone });
  if (!plan) return null;

  const resolution = resolveHistoryScope(plan, catalog);
  const followupPending = !!plan.followupReference && !plan.selectorTokens.length;
  const scopeErrors = followupPending
    ? scopePreserved(plan, resolution).filter(code => !['no_resolved_entities', 'pending_reference'].includes(code))
    : scopePreserved(plan, resolution);
  return {
    kind: 'investigation',
    history_class: 'entity_event_history',
    requires_general_tools: true,
    allowed_tool_pattern: null, // general read-only tools stay available
    plan,
    resolution,
    scope_errors: scopeErrors,
    followup_reference: followupPending,
    needs_clarification: followupPending ? false : (scopeErrors.includes('unresolved_scope') || scopeErrors.includes('scope_broadened') || scopeErrors.includes('mixed_entities_for_singular_request') || scopeErrors.includes('no_resolved_entities')),
    local_budget_ms: generalLocalMs,
    cloud_budget_ms: cloudMs,
    cloud_budget_is_fresh: true,
    preserve_completed_results: true,
    allow_writes: false,
    evidence_class: 'observed_metadata',
    reason: 'Device/event/recording history is a read-only investigation. Keep general read tools on both local and cloud, preserve the requested device/type/local-day scope, and separate observed recorder metadata from provider-authoritative history.',
    policy_version: policyVersion,
  };
}

/** Tool retention policy per route and phase ('local' | 'cloud'). */
export function toolPolicyFor(route, phase = 'local') {
  if (!route) return { keep: 'all', strip_non_mcp: false, allow_general: true };
  if (route.kind === 'history') {
    return { keep: 'ha-history', strip_non_mcp: true, allow_general: false, note: 'Person visit history: only recorded zone-history tools.' };
  }
  if (route.kind === 'investigation') {
    return { keep: 'all-read-only', strip_non_mcp: false, allow_general: true, note: 'Entity/event history: general read-only investigation tools must stay available on both local and cloud.' };
  }
  return { keep: 'all', strip_non_mcp: false, allow_general: true };
}

/** Whether a tool may run for this route. Writes are never allowed in history work. */
export function toolAllowedFor(route, toolName) {
  if (!route) return true;
  if (isWriteTool(toolName)) return false;
  if (route.kind === 'history') return /^ha[-_]history_/.test(String(toolName || '')) || /GetDateTime$/.test(String(toolName || ''));
  return true;
}

/**
 * Budget facts for a local step-limit / deadline message. Never fabricate a
 * "tool limit" and never state a capability denial on behalf of the harness.
 */
export function budgetNotice({ elapsed_ms = 0, local_budget_ms = 30000, steps = 0, max_steps = null, continuing_on_cloud = true } = {}) {
  const facts = [`${Math.round(elapsed_ms / 1000)}s of the ${Math.round(local_budget_ms / 1000)}s local budget used`];
  if (steps) facts.push(`${steps} local step${steps === 1 ? '' : 's'}`);
  const tail = continuing_on_cloud
    ? ' Completed tool results are preserved; the cloud continuation gets a fresh budget and must not replay completed writes.'
    : ' No capability conclusion should be drawn from this budget.';
  return `Local processing budget reached (${facts.join(', ')}).${tail}`;
}

/**
 * Filter a concrete tool catalog for a route. The important property for history
 * work is negative: no general tool is removed, and known HA write tools are
 * dropped because history answers are read-only. This is applied to the actual
 * emitted request body, not just to the classifier.
 */
export function filterToolDefinitions(route, names = []) {
  const kept = [], removed = [];
  for (const name of names) {
    if (!route || route.kind !== 'investigation') { kept.push(name); continue; }
    if (isWriteTool(name)) { removed.push(name); continue; }
    kept.push(name);
  }
  return { kept, removed };
}

/**
 * Whether the general local-first turn (and therefore the 30-second wall clock)
 * applies. A skipped scope must never be left without a timer: an investigation is
 * budgeted even when the semantic classifier is unavailable, because the
 * deterministic parser already identified it.
 */
export function generalBudgetApplies({ hasFiles = false, forbidden = false, requestKind = null, semanticKind = null, deterministicKind = null } = {}) {
  if (hasFiles || forbidden) return false;
  if (semanticKind === 'configuration') return false;
  if (requestKind === 'investigation' || deterministicKind === 'investigation') return true;
  if (requestKind || deterministicKind) return false; // HA device/history own their own budgets
  if (['devices', 'history'].includes(semanticKind)) return false;
  return true; // unknown general task: still gets the local-first budget
}

/**
 * Watchdog decision. A completed idle session must not switch models later; only a
 * turn that is still busy at its own deadline is handed over.
 */
export function shouldSwitchModelOnBudget({ idleAt = 0, busyAt = 0, startedAt = 0, alreadyFailed = false } = {}) {
  if (alreadyFailed) return false;
  if (idleAt >= busyAt && idleAt >= startedAt) return false;
  return true;
}

/**
 * Postcondition for a history answer: the requested scope must still be the scope
 * that was answered. Kept here so the plugin can refuse a broadened answer even if
 * the model produces one.
 */
export function answerScopeErrors(route, contract) {
  const errors = [];
  if (!route || route.kind !== 'investigation' || !contract) return errors;
  const requested = route.plan?.requested;
  const resolved = contract.resolved?.entities || [];
  if (!resolved.length) errors.push('answer_has_no_resolved_device_scope');
  if (requested?.plurality === 'singular' && resolved.length > 1) errors.push('answer_broadened_singular_request');
  if (route.plan?.window && contract.window?.date !== route.plan.window.date) errors.push('answer_window_differs_from_request');
  if (route.plan?.eventKinds?.length) {
    const kinds = new Set(contract.requested?.event_kinds || []);
    for (const kind of route.plan.eventKinds) if (!kinds.has(kind)) errors.push('answer_event_type_differs_from_request:' + kind);
  }
  return errors;
}
