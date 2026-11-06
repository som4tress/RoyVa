// Offline fixture: exercise the real Telegram command handler, never mutate Gmail.
import assert from 'node:assert/strict';
import {mkdtempSync, writeFileSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const command = process.argv[2];
const fail = process.argv[3] === 'fail';
const stale = process.argv[3] === 'stale';
const batch = process.argv[3] === 'batch';
const unbound = process.argv[3] === 'unbound' || batch;
const directory = mkdtempSync(join(tmpdir(), 'royva-permission-'));
const state = join(directory, 'state.json');
writeFileSync(state, JSON.stringify({offset: 0, messages: {'1:7': 'session'}, answers: {}, permissions: unbound ? {} : {'1:7': {sessionID: 'session', requestID: 'permission'}}}));
Object.assign(process.env, {TELEGRAM_BOT_TOKEN: 'fixture', TELEGRAM_ALLOWED_USER_IDS: '1', OPENCODE_TG_STATE_FILE: state, OPENCODE_TG_URL: 'http://fixture', OPENCODE_SERVER_PASSWORD: 'fixture', WHISPER_TMP: join(directory, 'whisper')});
let polled = false, submitted = false, nextID = 9;
const json = (value, status = 200) => new Response(JSON.stringify(value), {status, headers: {'content-type': 'application/json'}});
globalThis.fetch = async (url, options = {}) => {
  const body = options.body ? JSON.parse(options.body) : {};
  if (url.includes('api.telegram.org')) {
    const method = url.split('/').at(-1);
    if (method === 'getUpdates') {
      if (polled) return new Promise(() => {});
      polled = true;
      return json({ok: true, result: [{update_id: 1, message: {message_id: 8, chat: {id: 1}, from: {id: 1}, text: command, reply_to_message: {message_id: 7}}}]});
    }
    if (method === 'sendMessage') {
      if (stale) {assert(!submitted); assert.match(body.text, /no longer waiting/);}
      else if (unbound) {assert(!submitted); assert.match(body.text, /Permission required/); assert.match(body.text, batch ? /Action: Move 2 emails to Trash — this exact batch only/ : /Action: (Archive email|Move email to Trash)/);}
      else {assert(submitted);}
      if (fail) assert.match(body.text, /Could not confirm.*still waiting/);
      else if (!stale && !unbound) assert.equal(body.text, command === '/approve' ? 'Approved once.' : 'Denied.');
      setImmediate(() => {
        if (unbound) {const saved = JSON.parse(readFileSync(state)); if (batch) {assert.equal(saved.permissions['1:9'].requestID, 'permission');} else {assert.equal(saved.permissions['1:9'].requestID, 'other'); assert.equal(saved.permissions['1:10'].requestID, 'permission');}}
        rmSync(directory, {recursive: true, force: true}); console.log('Permission handler verified.'); process.exit(0);});
      return json({ok: true, result: {message_id: nextID++}});
    }
    return json({ok: true, result: method === 'getMe' ? {username: 'fixture'} : true});
  }
  const path = new URL(url).pathname;
  if (path === '/api/session/session/permission' && batch) return json({data: [{id: 'permission', action: 'gmail_batch_modify_messages', metadata: {input: {messageIds: ['first', 'second'], addLabelIds: ['TRASH'], removeLabelIds: ['INBOX']}}}]});
  if (path === '/api/session/session/permission') return json({data: [
    {id: 'other', action: 'gmail_modify_message', metadata: {input: {messageId: 'first', removeLabelIds: ['INBOX']}}},
    ...(!stale ? [{id: 'permission', action: 'gmail_modify_message', metadata: {input: {messageId: 'second', addLabelIds: ['TRASH']}}}] : []),
  ]});
  assert.equal(path, '/api/session/session/permission/permission/reply');
  assert.equal(options.method, 'POST');
  assert.deepEqual(body, {decision: command === '/approve' ? 'once' : 'reject'});
  submitted = true;
  return fail ? json({error: 'fixture'}, 400) : new Response(null, {status: 204});
};
const {main} = await import('./bridge.mjs');
await main({transcriber: async () => {throw Error('Unexpected transcription');}});
