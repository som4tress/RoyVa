const line = value => String(value ?? '').replace(/[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]/g, ' ');
function scrub(value, key = '') {
  if (typeof value === 'string') {
    if (/secret|password|token|authorization|api[_-]?key|credential/i.test(key) && !/(path|file|id|name)$/i.test(key)) return '[redacted]';
    return value.replace(/Bearer\s+[A-Za-z0-9._~+\/-]+/g, 'Bearer [redacted]');
  }
  if (Array.isArray(value)) return value.map(item => scrub(item, key));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, scrub(v, k)]));
  return value;
}
function emailDetails(rows, id) {
  if (!id) return;
  for (const row of [...rows].reverse()) for (const part of [...(row.content || [])].reverse()) {
    if (part.type !== 'tool' || !part.name?.startsWith('gmail_')) continue;
    for (const block of part.state?.content || []) {
      if (block.type !== 'text') continue;
      let data;
      try {data = JSON.parse(block.text);} catch {continue;}
      const messages = Array.isArray(data?.messages) ? data.messages : [data];
      const found = messages.find(message => message?.id === id);
      if (found) return found;
    }
  }
}

// One approval covers a whole request: after the user approves a bulk-tidy call, further calls of the SAME action in the SAME run
// (for example the next batch of a large mailbox) go through without asking again. Scoped per session and per action, capped, cleared when the run ends.
export const BATCH_TOOLS = new Set(['gmail-tidy_tidy_matching', 'gmail-tidy_tidy_ids']);
export function approvalKey(permission) {
  if (!BATCH_TOOLS.has(permission?.action)) return null;
  const action = permission.metadata?.input?.action;
  return typeof action === 'string' ? `gmail-tidy:${action}` : null;
}
export class BatchApprovals {
  constructor(cap = 25) { this.cap = cap; this.sessions = new Map(); }
  grant(session, key) { if (key) { if (!this.sessions.has(session)) this.sessions.set(session, new Map()); this.sessions.get(session).set(key, 0); } }
  take(session, key) {
    const keys = this.sessions.get(session);
    if (!key || !keys || !keys.has(key)) return false;
    const used = keys.get(key) + 1;
    if (used > this.cap) { keys.delete(key); return false; }
    keys.set(key, used);
    return true;
  }
  clear(session) { this.sessions.delete(session); }
}
const TIDY_VERB = { trash: 'Move to Trash', archive: 'Archive', mark_read: 'Mark as read', mark_unread: 'Mark as unread' };

export function formatPermission(permission, rows = []) {
  const input = permission.metadata?.input;
  const args = input && typeof input === 'object' ? input : {};
  const tool = permission.action;
  if (BATCH_TOOLS.has(tool)) {
    const verb = TIDY_VERB[args.action] || `Run ${line(args.action)}`;
    let what;
    if (tool.endsWith('_ids')) {
      const ids = Array.isArray(args.ids) ? args.ids : [];
      const senders = new Map();
      for (const id of ids) { const m = emailDetails(rows, id); if (m?.from) { const k = line(m.from).replace(/^.*<(.+)>.*$/, '$1').slice(0, 40); senders.set(k, (senders.get(k) || 0) + 1); } }
      const top = [...senders].sort((x, y) => y[1] - x[1]).slice(0, 3).map(([k, n]) => `${k} (${n})`).join(', ');
      what = `${ids.length} listed email${ids.length === 1 ? '' : 's'}${top ? `\nFrom: ${top}${senders.size > 3 ? ', …' : ''}` : ''}`;
    } else what = `every email matching: ${line(args.query).slice(0, 200)} (up to ${Number(args.limit) || 2000})`;
    return ['Approve?', `${verb}: ${what}`, '/approve or /deny'].join('\n');
  }
  let action = `Run ${line(tool)}`;
  const batch = tool === 'gmail_batch_modify_messages';
  if (tool === 'gmail_modify_message' || batch) {
    const add = Array.isArray(args.addLabelIds) ? args.addLabelIds : [];
    const remove = Array.isArray(args.removeLabelIds) ? args.removeLabelIds : [];
    if (add.some(label => remove.includes(label))) action = 'Conflicting email-label changes — review arguments';
    else {
      const effects = [];
      if (add.includes('TRASH')) effects.push('Move email to Trash');
      else if (add.includes('SPAM')) effects.push('Mark email as spam');
      else if (remove.includes('INBOX') && !add.includes('INBOX')) effects.push('Archive email (remove from Inbox; NOT move to Trash)');
      if (remove.includes('TRASH')) effects.push('Remove email from Trash');
      if (add.includes('INBOX')) effects.push('Move email into Inbox');
      if (add.includes('UNREAD')) effects.push('Mark unread');
      if (remove.includes('UNREAD')) effects.push('Mark read');
      if (add.includes('STARRED')) effects.push('Star email');
      if (remove.includes('STARRED')) effects.push('Unstar email');
      action = effects.join('; ') || 'Change email labels';
    }
  } else {
    action = {
      gmail_send_message: 'Send email', gmail_send_draft: 'Send existing draft',
      gmail_create_draft: 'Create email draft (not send)', gmail_create_label: 'Create Gmail label',
      'home-assistant-config_ha_config_set_automation': args.run_actions ? 'Save/update automation AND run its actions now' : args.config || args.python_transform ? 'Create/update Home Assistant automation' : 'Change automation enabled state',
      'home-assistant-config_ha_config_remove_automation': 'Delete Home Assistant automation',
      shell: 'Run shell command', edit: 'Edit file', write: 'Write file',
    }[tool] || action;
  }
  if (batch) action = action.replace(/\bemail(?= |$)/g, `${Array.isArray(args.messageIds) ? args.messageIds.length : '?'} emails`);
  const known = tool === 'gmail_modify_message';   // sends/drafts keep exact arguments: the body must be visible before approving
  const nativeAction = {
    HassTurnOn: 'Turn on targeted devices', HassTurnOff: 'Turn off targeted devices',
    HassLightSet: 'Change light brightness or colour', HassFanSetSpeed: 'Change fan speed',
    HassClimateSetTemperature: 'Change thermostat temperature', HassCancelAllTimers: 'Cancel ALL timers',
  }[String(tool).split('__').at(-1)];
  if (nativeAction) action = nativeAction;
  if (batch && Array.isArray(args.messageIds)) {
    // IDs and changes are displayed in full, never replaced with an open-ended query.
    action += '';
  }
  if (batch && Array.isArray(args.messageIds) && args.messageIds.length) {
    // Short summary: what, how many, from whom. The exact IDs stay in the tool call, not in the chat message.
    const found = args.messageIds.map(id => emailDetails(rows, id));
    const senders = new Map();
    for (const m of found) if (m?.from) { const k = line(m.from).replace(/^.*<(.+)>.*$/, '$1').slice(0, 40); senders.set(k, (senders.get(k) || 0) + 1); }
    const top = [...senders].sort((x, y) => y[1] - x[1]).slice(0, 3).map(([k, n]) => `${k} (${n})`).join(', ');
    const out = ['Approve?', action];
    if (top) out.push(`From: ${top}${senders.size > 3 ? ', …' : ''}`);
    const first = found.find(m => m?.subject);
    if (first) out.push(`e.g. "${line(first.subject).slice(0, 60)}"`);
    out.push('/approve or /deny (this batch only)');
    return out.join('\n');
  }
  // Short by design: what will happen, to what, and how to answer. Full arguments stay in the tool call, not in the chat.
  const details = emailDetails(rows, args.messageId);
  const lines = ['Approve?', action];
  if (details?.subject) lines.push(`Subject: ${line(details.subject).slice(0, 80)}`);
  if (details?.from) lines.push(`From: ${line(details.from).slice(0, 60)}`);
  for (const [key, label] of [['to', 'To'], ['cc', 'CC'], ['bcc', 'BCC'], ['subject', 'Subject']]) {
    if (args[key] && !(key === 'subject' && details?.subject)) lines.push(`${label}: ${line(args[key]).slice(0, 80)}`);
  }
  if (tool === 'gmail_send_draft') lines.push('Review the draft first: this approval does not show its recipients or text.');
  if (!details && input !== undefined && !lines.some(l => l.startsWith('To:'))) {
    const brief = JSON.stringify(scrub(input));
    if (brief && brief !== '{}') lines.push(`Details: ${brief.length > 220 ? brief.slice(0, 220) + '…' : brief}`);
  }
  lines.push('/approve or /deny');
  return lines.join('\n');
}
