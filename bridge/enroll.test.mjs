import test from 'node:test';
import assert from 'node:assert/strict';
import {makeEnrollment, LiveAllowlist, looksLikeSignin, parseCommand} from './enroll.mjs';

const msg = (text, id = 7) => ({text, from: {id, first_name: 'Alice'}});
function rig(responses = {}) {
  const calls = [], said = [], told = [];
  const allowlist = {refresh: async () => {}};
  const call = async (path, body) => { calls.push([path, body]); return responses[path] ?? {ok: true}; };
  const e = makeEnrollment({call, reply: async (m, t) => said.push(t), tell: async (id, t) => told.push([id, t]), allowlist});
  return {e, calls, said, told};
}

test('a stranger is ignored unless they send a valid-looking invite code', async () => {
  const r = rig();
  for (const t of ['hello', 'how many unread emails', '/join', '/join nonsense', '/people', 'cc: hi', '/start']) assert.equal(await r.e.handleStranger(msg(t)), false);
  assert.deepEqual(r.calls, []); assert.deepEqual(r.said, []);                 // nothing sent to the gateway, no reply to the stranger
});

test('a stranger with a code (deep link or /join) is forwarded as join and the owner is told', async () => {
  const r = rig({'/v1/enroll/join': {ok: true, name: 'alice', display: 'Alice', owners: ['1']}});
  assert.equal(await r.e.handleStranger(msg('/start K7QX-4WZ9')), true);
  assert.deepEqual(r.calls[0], ['/v1/enroll/join', {user: 'telegram:7', code: 'K7QX-4WZ9', display: 'Alice'}]);
  assert.match(r.told[0][1], /\/accept alice/); assert.equal(r.told[0][0], '1');
  assert.match(r.said[0], /asked the owner/);
});

test('a failed join shows the gateway error and notifies nobody', async () => {
  const r = rig({'/v1/enroll/join': {ok: false, error: 'That code is not valid'}});
  await r.e.handleStranger(msg('/join AAAA-BBBB'));
  assert.deepEqual(r.said, ['That code is not valid']); assert.deepEqual(r.told, []);
});

test('a pasted sign-in address goes only to the gateway finish call, with &amp; fixed, and is never left for the model', async () => {
  const r = rig({'/v1/enroll/gmail/finish': {ok: true, mode: 'readonly'}});
  const handled = await r.e.handleMember(msg('http://localhost:3000/oauth2callback?state=ab12&amp;code=4/0xyz&amp;scope=s'));
  assert.equal(handled, true);
  assert.equal(r.calls[0][0], '/v1/enroll/gmail/finish');
  assert.match(r.calls[0][1].text, /&code=4\/0xyz&scope/);
  assert.doesNotMatch(r.said.join(' '), /4\/0xyz/);                              // the code is never echoed back
});

test('normal questions are not enrollment and fall through to the model', async () => {
  const r = rig();
  for (const t of ['How many unread emails?', 'code review tips', 'turn on the lights', '/start', '/help']) assert.equal(await r.e.handleMember(msg(t)), false);
  assert.deepEqual(r.calls, []);
});

test('invite, people, accept, decline, revoke and connect-gmail call the right gateway routes with the sender identity', async () => {
  const r = rig({'/v1/enroll/invite': {ok: true, name: 'alice', code: 'K7QX-4WZ9', expires_in_hours: 24},
                 '/v1/enroll/decide': {ok: true, approved: true, name: 'alice', user: 'telegram:7'},
                 '/v1/enroll/people': {ok: true, people: [{name: 'boss', role: 'owner', mail: 'default'}]},
                 '/v1/enroll/revoke': {ok: true, name: 'alice', mailbox_removed: true},
                 '/v1/enroll/gmail/start': {ok: true, url: 'https://accounts.google.com/x'}});
  const owner = msg('/invite alice alice@gmail.com', 1);
  await r.e.handleMember(owner);
  await r.e.handleMember(msg('/people', 1));
  await r.e.handleMember(msg('/accept alice', 1));
  await r.e.handleMember(msg('/revoke alice', 1));
  await r.e.handleMember(msg('/connect-gmail', 7));
  assert.deepEqual(r.calls.map(c => [c[0], c[1].user]), [['/v1/enroll/invite', 'telegram:1'], ['/v1/enroll/people', 'telegram:1'],
    ['/v1/enroll/decide', 'telegram:1'], ['/v1/enroll/revoke', 'telegram:1'], ['/v1/enroll/gmail/start', 'telegram:7']]);
  assert.equal(r.calls[0][1].gmail, 'alice@gmail.com');
  assert.match(r.said[0], /test user/); assert.match(r.said[0], /start=K7QX-4WZ9/);
  assert.deepEqual(r.told[0], ['7', 'You are in! Ask me anything. To connect your own Gmail, send /connect-gmail.']);
});

test('the live allowlist keeps env owners, adds enrolled ids, caches, and survives a gateway outage', async () => {
  let n = 0, fail = false, t = 0;
  const wl = new LiveAllowlist(['1'], async () => { n++; if (fail) throw new Error('down'); return {ids: ['2'], owners: ['1']}; }, {ttlMs: 1000, now: () => t});
  assert.equal(await wl.has('1'), true); assert.equal(await wl.has('2'), true); assert.equal(await wl.has('3'), false);
  assert.equal(n, 1);                                                         // cached
  t = 2000; fail = true;
  assert.equal(await wl.has('2'), true);                                      // outage: last good copy stays
  fail = false; wl.ids = new Set(); await wl.refresh(true); assert.equal(await wl.has('2'), true);
  assert.equal(await wl.isOwner('1'), true); assert.equal(await wl.isOwner('2'), false);
});

test('a message with words around a pasted address is a normal message (it must reach Claude/RoyVa), not a sign-in', async () => {
  const r = rig();
  const text = '/claude see i again got this link\n\nlocalhost:3000/oauth2callback?state=ab12&iss=x&code=4/0xyz&scope=s\n\nisn\u2019t this a problem';
  assert.equal(looksLikeSignin(text), false);
  assert.equal(await r.e.handleMember(msg(text)), false);
  assert.deepEqual(r.calls, []);
  assert.equal(looksLikeSignin('localhost:3000/oauth2callback?state=ab12&iss=x&code=4/0xyz&scope=s'), true);   // the bare address (no http://) still counts
});

test('helpers', () => {
  assert.equal(looksLikeSignin('0123456789abcdef0123456789abcdef.4/0Abc'), true);
  assert.equal(looksLikeSignin('state=ab&code=1'), true);
  assert.equal(looksLikeSignin('what is the code for the door'), false);
  assert.deepEqual(parseCommand('/invite@roy_has_bot alice a@b.co'), {cmd: 'invite', args: ['alice', 'a@b.co']});
  assert.equal(parseCommand('hello'), null);
});

test('after a Gmail sign-in the owner is told, OpenCode restart is scheduled, and disconnect also schedules it', async () => {
  let restarts = 0;
  const calls = [], said = [], told = [];
  const r = {call: async (p, b) => { calls.push(p); return p.endsWith('/finish') ? {ok: true, name: 'alice', mode: 'readonly', needs_restart: true, owners: ['1']} : {ok: true, had_connection: true, needs_restart: true}; }};
  const e = makeEnrollment({call: r.call, reply: async (m, t) => said.push(t), tell: async (id, t) => told.push([id, t]), allowlist: {refresh: async () => {}}, restartWhenIdle: async () => { restarts++; }});
  await e.handleMember(msg('http://localhost:3000/oauth2callback?state=ab&code=1'));
  assert.equal(restarts, 1); assert.match(told[0][1], /alice connected their Gmail/);
  await e.handleMember(msg('/disconnect-gmail'));
  assert.equal(restarts, 2); assert.match(said.at(-1), /disconnected/);
});
