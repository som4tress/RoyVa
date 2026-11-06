// Offline bridge fixture: all Telegram/OpenCode traffic and transcription are mocked.
import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const root = mkdtempSync(join(tmpdir(), 'royva-voice-test-'));
Object.assign(process.env, {
  TELEGRAM_BOT_TOKEN: 'fixture', TELEGRAM_ALLOWED_USER_IDS: '1',
  OPENCODE_TG_STATE_FILE: join(root, 'state.json'), WHISPER_TMP: join(root, 'whisper'),
  OPENCODE_TG_URL: 'http://fixture', OPENCODE_SERVER_PASSWORD: 'fixture',
  OPENCODE_TG_DIR: root,
});
const sends = [];
let admitted = false, polled = false, nextID = 100, transcribed = false;
const json = value => new Response(JSON.stringify(value), {headers: {'content-type': 'application/json'}});
globalThis.fetch = async (url, options = {}) => {
  const body = options.body ? JSON.parse(options.body) : {};
  if (url.includes('/file/bot')) return new Response(new Uint8Array([1, 2, 3]));
  if (url.startsWith('https://api.telegram.org/')) {
    const method = url.split('/').at(-1);
    let result = true;
    if (method === 'getMe') result = {username: 'fixture'};
    if (method === 'getUpdates') {
      if (polled) return new Promise(() => {});
      polled = true;
      result = [{update_id: 1, message: {message_id: 7, chat: {id: 1}, from: {id: 1}, voice: {file_id: 'audio', duration: 1, file_size: 3}}}];
    }
    if (method === 'getFile') result = {file_path: 'audio.ogg'};
    if (method === 'sendMessage') {
      assert(transcribed, 'No progress or answer before transcription finishes');
      result = {message_id: nextID++};
      sends.push({...body, message_id: result.message_id});
      if (body.text === 'I am RoyVa.') setImmediate(() => {
        try {
          assert.equal(sends.length, 3);
          const [transcript, progress, answer] = sends;
          assert.equal(transcript.text, 'Hi, who are you?');
          assert.equal(transcript.reply_parameters.message_id, 7);
          assert.equal(progress.reply_parameters.message_id, transcript.message_id);
          assert.equal(answer.reply_parameters.message_id, transcript.message_id);
          const state = JSON.parse(readFileSync(process.env.OPENCODE_TG_STATE_FILE));
          assert.equal(state.messages[`1:${transcript.message_id}`], 'session');
          console.log('Voice transcript, progress and final reply routing verified.');
          rmSync(root, {recursive: true, force: true});
          process.exit(0);
        } catch (error) {console.error(error); process.exit(1);}
      });
    }
    return json({ok: true, result});
  }
  const path = new URL(url).pathname;
  if (path === '/api/session') return json({data: {id: 'session'}});
  if (path.endsWith('/prompt')) {
    assert.equal(body.text, 'Hi, who are you?');
    admitted = true; return json({data: {}});
  }
  if (path.endsWith('/permission')) return json({data: []});
  if (path.endsWith('/message')) return json({data: admitted ? [
    {id: 'user', type: 'user', time: {created: 1}},
    {id: 'answer', type: 'assistant', time: {created: 2, completed: 2}, content: [{type: 'text', text: 'I am RoyVa.'}]},
  ] : []});
  if (path === '/api/session/session') return json({data: {time: {idle: 3, busy: 1}}});
  throw new Error(`Unexpected mocked request ${path}`);
};
const {main} = await import('./bridge.mjs');
await main({transcriber: async () => {transcribed = true; return {ok: true, text: 'Hi, who are you?'};}});
