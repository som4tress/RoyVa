// Runaway-loop guard. A run is stopped only when it is actually stuck, or at a high hard ceiling; a long but progressing job (many different calls) is left alone.
const SKIP = new Set(['text', 'reasoning', 'thinking', 'step-start', 'step-finish']);
export const REPEAT_LIMIT = 3;        // the same call (same tool, same inputs) this many times = going in circles
export const ERROR_STREAK = 4;        // this many failed calls in a row = not getting anywhere
export const HARD_ROUNDS = 25;        // absolute ceiling on model rounds, whatever the skill's own step count says
export const HARD_CALLS = 80;

const toolParts = row => (row.content || []).filter(part => part.type && !SKIP.has(part.type));

// rows: the session's messages for this run. Returns null (carry on) or a short reason string (stop and ask for a wrap-up).
export function loopVerdict(rows, {hardRounds = HARD_ROUNDS, hardCalls = HARD_CALLS} = {}) {
  const assistants = rows.filter(row => row.type === 'assistant');
  const parts = assistants.flatMap(toolParts);
  const rounds = assistants.filter(row => toolParts(row).length).length;
  if (rounds > hardRounds) return `${rounds} rounds (ceiling ${hardRounds})`;
  if (parts.length > hardCalls) return `${parts.length} calls (ceiling ${hardCalls})`;
  // "Going in circles" = the same call, again, in a LATER round, after it already finished. Identical calls fired together in one round
  // (models do that) and calls still running are not repeats, and an interrupted call never counts.
  const seen = new Map();
  for (const row of assistants) {
    const inRound = new Set();
    for (const part of toolParts(row)) {
      const status = part.state?.status;
      if (status !== 'completed' && !(status === 'error' && part.state?.error?.type !== 'aborted')) continue;
      inRound.add(`${part.name}\u0000${JSON.stringify(part.state?.input ?? null)}`);
    }
    for (const key of inRound) {
      seen.set(key, (seen.get(key) || 0) + 1);
      if (seen.get(key) >= REPEAT_LIMIT) return `the same call (${key.split('\u0000')[0]}) in ${REPEAT_LIMIT} separate rounds`;
    }
  }
  let streak = 0;
  for (const part of parts) {
    streak = part.state?.status === 'error' && part.state?.error?.type !== 'aborted' ? streak + 1 : 0;       // an interrupted call is not a failure
    if (streak >= ERROR_STREAK) return `${ERROR_STREAK} failed calls in a row`;
  }
  return null;
}
