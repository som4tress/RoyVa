// Telegram side of enrollment. Pure logic over injected functions so it can be tested without Telegram or the gateway.
// Identity always comes from Telegram (message.from.id), never from message text. The gateway enforces owner rights; the bridge only routes.
const CODE = /\b([A-Za-z0-9]{4}-[A-Za-z0-9]{4})\b/;
const SIGNIN = /[?&]code=[^\s]+[\s\S]*state=|state=[^\s]+[\s\S]*[?&]code=|^[0-9a-f]{32}\.\S+$/;

// A sign-in paste is ONE token (the address or code, nothing else). A message with words around it ("cc: look at this link ...") is a normal message.
export const looksLikeSignin = text => { const t = String(text || '').replace(/&amp;/g, '&').trim(); return /^\S+$/.test(t) && SIGNIN.test(t); };

export function parseCommand(text) {
  const t = String(text || '').trim();
  const m = /^\/(invite|join|start|people|accept|decline|revoke|connect-gmail|connect_gmail|connect-email|disconnect-gmail)(?:@\w+)?(?:\s+([\s\S]*))?$/i.exec(t);
  if (!m) return null;
  return {cmd: m[1].toLowerCase().replace('_', '-').replace('connect-email', 'connect-gmail'), args: (m[2] || '').trim().split(/\s+/).filter(Boolean)};
}

// Live allowlist: the env owner list is always allowed; enrolled people come from the gateway (cached briefly; on error keep the last good copy).
export class LiveAllowlist {
  constructor(envIds, fetchIds, {ttlMs = 15000, now = Date.now} = {}) {
    this.env = new Set(envIds); this.fetchIds = fetchIds; this.ttlMs = ttlMs; this.now = now;
    this.ids = new Set(); this.owners = new Set(); this.at = -Infinity;
  }
  async refresh(force = false) {
    if (!force && this.now() - this.at < this.ttlMs) return;
    this.at = this.now();
    try {
      const r = await this.fetchIds();
      this.ids = new Set((r.ids || []).map(String)); this.owners = new Set((r.owners || []).map(String));
    } catch { /* gateway down: keep the previous copy; the env owners still work */ }
  }
  async has(id) { await this.refresh(); return this.env.has(String(id)) || this.ids.has(String(id)); }
  async isOwner(id) { await this.refresh(); return this.owners.has(String(id)) || (this.owners.size === 0 && this.env.has(String(id)) && this.env.size === 1); }
}

export function makeEnrollment({call, reply, tell, allowlist, restartWhenIdle = async () => {}}) {
  const user = m => `telegram:${m.from.id}`;
  const fmt = {
    people: list => list.map(p => `• ${p.name} (${p.role}${p.mail ? `, mail: ${p.mail}` : ''})`).join('\n') || 'Nobody yet.',
  };
  const must = async (path, body) => { const r = await call(path, body); return r; };

  // A sender who is not (yet) allowed. Only a valid-looking invite code is ever looked at; everything else is ignored silently.
  async function handleStranger(message) {
    const c = parseCommand(message.text);
    if (!c || !['start', 'join'].includes(c.cmd)) return false;
    const code = c.args.join(' ').match(CODE)?.[1];
    if (!code) return false;
    const r = await must('/v1/enroll/join', {user: user(message), code, display: [message.from.first_name, message.from.last_name].filter(Boolean).join(' ')});
    if (!r.ok) { await reply(message, r.error); return true; }
    await reply(message, 'Thanks! I asked the owner to approve you. You will get a message when it is done.');
    for (const owner of r.owners || [])
      await tell(owner, `${r.name} (${r.display || 'Telegram user'}) wants to join RoyVa.\n/accept ${r.name}  or  /decline ${r.name}`);
    return true;
  }

  // An allowed sender. Returns true when the message was an enrollment command (so it never reaches the model).
  async function handleMember(message) {
    const text = message.text || '';
    if (looksLikeSignin(text)) {                                   // a pasted sign-in address/code: straight to the gateway, never to the model
      const r = await must('/v1/enroll/gmail/finish', {user: user(message), text: text.replace(/&amp;/g, '&')});
      await reply(message, r.ok
        ? `Gmail connected (${r.mode === 'manage' ? 'read and organise' : 'read only'}). It becomes available in about a minute.`
        : r.error);
      if (r.ok) {
        for (const owner of r.owners || []) await tell(owner, `${r.name} connected their Gmail (${r.mode === 'manage' ? 'read and organise' : 'read only'}).`);
        if (r.needs_restart) void restartWhenIdle();               // OpenCode must reload to see the new Gmail servers; done when no run is active
      }
      return true;
    }
    const c = parseCommand(text);
    if (!c) return false;
    const u = user(message);
    switch (c.cmd) {
      case 'invite': {
        const [name, gmail] = c.args;
        if (!name) { await reply(message, 'Usage: /invite <name> [their-gmail-address]'); return true; }
        const r = await must('/v1/enroll/invite', {user: u, name, gmail: gmail || ''});
        await reply(message, r.ok
          ? `Invite for ${r.name}. Code ${r.code} (one use, ${r.expires_in_hours} h). They open t.me/roy_has_bot?start=${r.code} or send /join ${r.code}.` +
            `\nIf they will connect Gmail: while the Google app is in Testing mode, add their address as a test user in Google Cloud first.`
          : r.error);
        return true;
      }
      case 'people': { const r = await must('/v1/enroll/people', {user: u}); await reply(message, r.ok ? fmt.people(r.people) : r.error); return true; }
      case 'accept': case 'decline': {
        const r = await must('/v1/enroll/decide', {user: u, name: c.args[0] || '', approve: c.cmd === 'accept'});
        if (!r.ok) { await reply(message, r.error); return true; }
        await allowlist.refresh(true);
        await reply(message, r.approved ? `${r.name} is in. They can use the home and general skills; no email unless they connect their own.` : `${r.name} was declined.`);
        await tell(r.user.split(':')[1], r.approved
          ? 'You are in! Ask me anything. To connect your own Gmail, send /connect-gmail.' : 'Sorry, the owner did not approve this request.');
        return true;
      }
      case 'revoke': {
        const r = await must('/v1/enroll/revoke', {user: u, name: c.args[0] || ''});
        if (r.ok) await allowlist.refresh(true);
        await reply(message, r.ok ? `${r.name} removed${r.mailbox_removed ? ' (their Gmail connection was deleted too)' : ''}.` : r.error);
        return true;
      }
      case 'connect-gmail': {
        const r = await must('/v1/enroll/gmail/start', {user: u, manage: c.args.includes('manage')});
        await reply(message, r.ok
          ? `Open this link, sign in with your Gmail account and tick every box:\n${r.url}\n\nAt the end you will see either a page with a code (tap Copy) or a page that cannot be reached whose address starts with localhost. Paste the code, or that full address, here as a message by itself. The link works for 10 minutes.`
          : r.error);
        return true;
      }
      case 'disconnect-gmail': {
        const r = await must('/v1/enroll/gmail/stop', {user: u});
        await reply(message, r.ok ? (r.had_connection ? 'Your Gmail was disconnected and its access token deleted.' : 'No Gmail was connected.') : r.error);
        if (r.ok && r.needs_restart) void restartWhenIdle();
        return true;
      }
      case 'join': case 'start': return false;                       // /start for an existing user is the normal help text
      default: return false;
    }
  }
  return {handleStranger, handleMember};
}
