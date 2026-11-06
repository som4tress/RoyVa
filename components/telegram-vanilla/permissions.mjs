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

export function formatPermission(permission, rows = []) {
  const input = permission.metadata?.input;
  const args = input && typeof input === 'object' ? input : {};
  const tool = permission.action;
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
  const nativeAction = {
    HassTurnOn: 'Turn on targeted devices', HassTurnOff: 'Turn off targeted devices',
    HassLightSet: 'Change light brightness or colour', HassFanSetSpeed: 'Change fan speed',
    HassClimateSetTemperature: 'Change thermostat temperature', HassCancelAllTimers: 'Cancel ALL timers',
  }[String(tool).split('__').at(-1)];
  if (nativeAction) action = nativeAction;
  if (batch && Array.isArray(args.messageIds)) {
    // IDs and changes are displayed in full, never replaced with an open-ended query.
    action += ' — this exact batch only';
  }
  const details = emailDetails(rows, args.messageId);
  const lines = ['Permission required', `Action: ${action}`];
  if (details?.subject) lines.push(`Subject: ${line(details.subject)}`);
  if (details?.from) lines.push(`From: ${line(details.from)}`);
  for (const [key, label] of [['messageId', 'Email ID'], ['draftId', 'Draft ID'], ['to', 'To'], ['cc', 'CC'], ['bcc', 'BCC'], ['subject', 'Subject']]) {
    if (args[key]) lines.push(`${label}: ${line(args[key])}`);
  }
  if (tool === 'gmail_send_draft') lines.push('This call supplies a draft ID, not its current recipients/body. Review the draft before approving.');
  if (batch && Array.isArray(args.messageIds)) {
    lines.push('Messages in this batch:');
    for (const id of args.messageIds) {
      const message = emailDetails(rows, id);
      lines.push(`- ${line(id)}${message?.subject ? ` | ${line(message.subject)}` : ''}${message?.from ? ` | ${line(message.from)}` : ''}`);
    }
    lines.push('This approval does not cover later batches, pages or requests.');
  }
  lines.push(`Tool: ${line(tool)}`);
  if (input !== undefined) lines.push('Exact arguments (secret fields redacted):', JSON.stringify(scrub(input), null, 2));
  else lines.push('Arguments: not provided by the tool.');
  if (permission.resources?.length) lines.push(`Permission resources: ${permission.resources.map(line).join(', ')}`);
  lines.push('Reply to this message with /approve to allow this call once, or /deny.');
  return lines.join('\n');
}
