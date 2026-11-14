import {createHash} from 'node:crypto';
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
    if (part.type !== 'tool' || !canonTool(part.name)?.startsWith('gmail_')) continue;
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
// A person's own mailbox is served by gmail-u-<person> / gmail-tidy-u-<person>; everything below reasons about the canonical gmail_* / gmail-tidy_* names.
const MAIL_NAME = /^(gmail-tidy|gmail)(?:-u-([a-z0-9][a-z0-9-]*))?_(.+)$/;
export const canonTool = name => { const m = typeof name === 'string' && MAIL_NAME.exec(name); return m ? `${m[1]}_${m[3]}` : name; };
export const mailAccount = name => { const m = typeof name === 'string' && MAIL_NAME.exec(name); return m ? (m[2] || 'default') : null; };
export const BATCH_TOOLS = new Set(['gmail-tidy_tidy_matching', 'gmail-tidy_tidy_ids']);
export function approvalKey(permission) {
  if (!BATCH_TOOLS.has(canonTool(permission?.action))) return null;
  const action = permission.metadata?.input?.action;
  if (typeof action !== 'string') return null;
  const acct = mailAccount(permission.action);                       // an approval never carries across mailboxes
  return acct && acct !== 'default' ? `gmail-tidy:${acct}:${action}` : `gmail-tidy:${action}`;
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


// The call only carries ids. The names shown beside them come from Home Assistant itself, asked at the moment of the prompt (gateway /v1/resolve-ids),
// never from the model or from earlier conversation. An id Home Assistant does not know, or a failed lookup, makes the request unverified: it can only be denied.
const LABEL = {device_id: 'Device', entity_id: 'Entity', area_id: 'Area', floor_id: 'Floor'};
export function idsInArgs(args) {
  const out = {device_id: [], entity_id: [], area_id: [], floor_id: []};
  const scan = (value, key) => {
    if (Array.isArray(value)) return value.forEach(v => scan(v, key));
    if (value && typeof value === 'object') return Object.entries(value).forEach(([k, v]) => scan(v, k));
    if (typeof value === 'string' && out[key] && !out[key].includes(value)) out[key].push(value);
  };
  scan(args?.params ?? {}, '');
  return out;
}
export const hasIds = ids => Object.values(ids).some(list => list.length);
// live = the gateway's {kind: {id: {name}}} answer, or null when the lookup failed. Returns the lines to show and whether every id was matched.
export function verifyIds(args, live) {
  const ids = idsInArgs(args);
  if (!hasIds(ids)) return {lines: [], verified: true};
  if (!live) return {lines: ['⚠ Could not check these ids against Home Assistant, so the names are unverified.'], verified: false};
  const lines = [];
  let verified = true;
  for (const [key, list] of Object.entries(ids)) for (const id of list) {
    const hit = live[key]?.[id];
    if (hit) lines.push(`${LABEL[key]}: ${hit.name ? line(hit.name) : '(no display name)'}  [${line(id)}]`);
    else { verified = false; lines.push(`⚠ ${LABEL[key]} ${line(id)} does not exist in Home Assistant`); }
  }
  return {lines, verified};
}
export const permissionVerified = (permission, live) => !FULL_CALL[canonTool(permission.action)] || verifyIds(permission.metadata?.input || {}, live).verified;
export const FULL_CALL = {'ha-api_ha_write': 'Change Home Assistant through its API:', 'ha-api_ha_edit': 'Edit a saved Home Assistant item:', 'machine_run_approved': 'Run on THIS machine:', 'machine_remote_run_approved': 'Run on a REMOTE machine:'};
const FULL_LIMIT = 3500;
// A stable fingerprint of exactly what will run. It is taken when the card is shown and checked again when the owner approves, so what was reviewed is what runs.
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])])) : value;
export const callHash = input => createHash('sha256').update(JSON.stringify(canonical(input ?? null))).digest('hex');
// Calls too long for a card are attached as a file instead (never truncated, never refused for size). null = fits in the card.
export function fullCallFile(permission) {
  const tool = canonTool(permission?.action);
  if (!FULL_CALL[tool]) return null;
  const input = permission.metadata?.input && typeof permission.metadata.input === 'object' ? permission.metadata.input : {};
  const body = JSON.stringify(scrub(input), null, 1);
  return body.length > FULL_LIMIT ? {name: `call-${callHash(input).slice(0, 8)}.json`, content: body} : null;
}
const DIFF_SHOWN = 25;
// extra.preview comes from the gateway (/v1/preview-edit): {ok, problem, lines, edits, renders}, or null when it could not be built. Without a good preview there is no Approve.
export const editBlocked = extra => !extra?.preview || extra.preview.ok !== true;
function formatEdit(args, extra) {
  const pv = extra?.preview;
  const out = ['Approve?', `Edit a saved Home Assistant ${line(args.domain)}: ${line(args.id)}`];
  const edits = Array.isArray(pv?.edits) && pv.edits.length ? pv.edits : (Array.isArray(args.edits) ? args.edits.map(e => `${line(e?.op)} ${line(e?.path)}`) : []);
  out.push('Edits:', ...edits.slice(0, 10).map(e => `• ${line(e).slice(0, 200)}`));
  if (pv?.lines) out.push(pv.lines.length ? 'Changes compared with what is saved now:' : 'No difference from what is saved now.', ...pv.lines.slice(0, DIFF_SHOWN), ...(pv.lines.length > DIFF_SHOWN ? [`… and ${pv.lines.length - DIFF_SHOWN} more`] : []));
  for (const r of pv?.renders || []) {
    if (r.status === 'ok') out.push(`Renders now at ${line(r.path)}: ${line(r.rendered).slice(0, 200)}`);
    else if (r.status === 'needs_context') out.push(`Added text at ${line(r.path)} uses the automation's own variables, so it could not be tested alone.`);
    else if (r.status === 'error') out.push(`⚠ Added text at ${line(r.path)} fails: ${line(r.error).slice(0, 200)}`);
  }
  if (!pv) out.push('⚠ Could not build a preview of this edit, so it cannot be reviewed.');
  else if (pv.problem) out.push(`⚠ ${line(pv.problem).slice(0, 300)}`);
  out.push(editBlocked(extra) ? 'Approve is disabled: /deny' : '/approve or /deny (this edit only)');
  return out.join('\n');
}
// extra: {attached: bool|undefined, diff: string[]|null|undefined}. attached=false means the file was needed but could not be sent: Approve must stay disabled.
export function formatPermission(permission, rows = [], live = undefined, extra = {}) {
  const input = permission.metadata?.input;
  const args = input && typeof input === 'object' ? input : {};
  const tool = canonTool(permission.action);
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
    return ['Approve?', `${verb}: ${what}`, '/approve (covers the whole request) or /deny'].join('\n');
  }
  if (tool === 'ha-api_ha_edit') return formatEdit(args, extra);
  if (FULL_CALL[tool]) {
    const check = verifyIds(args, live);
    const names = check.lines;                                    // arbitrary-power tools: show the whole call (escaped, so nothing hides in a newline), never a truncated one
    const body = JSON.stringify(scrub(args), null, 1);
    const tooLong = body.length > FULL_LIMIT;
    const out = ['Approve?', FULL_CALL[tool], ...names];
    if (!tooLong) out.push(body);
    else if (extra.attached) out.push(`The full call (${body.length} characters, id ${callHash(args).slice(0, 8)}) is attached above as a file. Read it before approving: that call will run (secret-looking values are shown as [redacted] here but are sent as they are).`);
    else out.push(`⚠ The full call is ${body.length} characters and could not be attached, so it cannot be reviewed here. Approve is disabled: /deny`);
    if (Array.isArray(extra.diff)) {
      if (extra.diff.length) out.push('Changes compared with what is saved now:', ...extra.diff.slice(0, DIFF_SHOWN), ...(extra.diff.length > DIFF_SHOWN ? [`… and ${extra.diff.length - DIFF_SHOWN} more (see the attached file)`] : []));
      else out.push('No difference from what is saved now.');
    } else if (extra.diff === null) out.push('(Could not compare with what is saved now.)');
    out.push(check.verified && !(tooLong && !extra.attached) ? '/approve or /deny (this call only)' : 'Approve is disabled: /deny');
    return out.join('\n');
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
  for (const [key, label] of [['to', 'To'], ['cc', 'CC'], ['bcc', 'BCC'], ['subject', 'Subject'], ['body', 'Text']]) {
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

// The owner-only doors (shell on this and other machines, the Home Assistant write API) must never reach a remote model: the DeepSeek takeover runs with every permission
// pre-allowed, so any server left in its config would run without the owner's approval.
export const OWNER_DOOR_SERVERS = ['machine', 'ha-api'];
export function withoutOwnerDoors(config) {
  const out = structuredClone(config);
  for (const name of OWNER_DOOR_SERVERS) if (out.mcp?.servers) delete out.mcp.servers[name];
  return out;
}
