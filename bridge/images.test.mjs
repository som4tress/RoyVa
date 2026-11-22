import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { generatedImages, imageCaptions, sendPhotos, retryMs, floodMs, resetFlood } from './images.mjs';

const dir = mkdtempSync(join(tmpdir(), 'imgs-'));
const good = join(dir, 'a.png'); writeFileSync(good, Buffer.alloc(2000));
const call = (name, status, payload) => ({ type: 'assistant', content: [{ type: 'tool', name, state: { status, content: [{ type: 'text', text: JSON.stringify(payload) }] } }] });

test('collects the picture from a completed generate_image call', () => {
  assert.deepEqual(generatedImages([call('image-gen_generate_image', 'completed', { ok: true, image_path: good })], dir), [good]);
});
test('ignores failures, other tools, errors, missing files and duplicates', () => {
  const rows = [call('image-gen_generate_image', 'completed', { ok: false, error: 'busy' }), call('ha-speakers_speak', 'completed', { ok: true, image_path: good }),
    call('image-gen_generate_image', 'error', { ok: true, image_path: good }), call('image-gen_generate_image', 'completed', { ok: true, image_path: join(dir, 'gone.png') }),
    call('image-gen_generate_image', 'completed', { ok: true, image_path: good }), call('image-gen_generate_image', 'completed', { ok: true, image_path: good })];
  assert.deepEqual(generatedImages(rows, dir), [good]);
});
test('never uploads a file outside the images folder (even if a tool result names one)', () => {
  const other = mkdtempSync(join(tmpdir(), 'other-')); const evil = join(other, 'secret.png'); writeFileSync(evil, Buffer.alloc(2000));
  assert.deepEqual(generatedImages([call('image-gen_generate_image', 'completed', { ok: true, image_path: evil })], dir), []);
  assert.deepEqual(generatedImages([call('image-gen_generate_image', 'completed', { ok: true, image_path: join(dir, '..', 'x.png') })], dir), []);
});
test('sendPhotos posts each file to sendPhoto with the reply target, and throws when Telegram refuses', async () => {
  const seen = [];
  await sendPhotos('TOKEN', 42, [good], 7, async (url, init) => { seen.push([url, init.body.get('chat_id'), init.body.get('reply_parameters'), init.body.get('photo').type]); return { json: async () => ({ ok: true }) }; });
  assert.deepEqual(seen, [['https://api.telegram.org/botTOKEN/sendPhoto', '42', JSON.stringify({ message_id: 7, allow_sending_without_reply: true }), 'image/png']]);
  await assert.rejects(sendPhotos('T', 1, [good], 0, async () => ({ json: async () => ({ ok: false, error_code: 400 }) })), /sendPhoto: 400/);
});
test('retries a Telegram rate limit (429) after the requested wait, then succeeds; gives up after a few tries', async () => {
  let calls = 0;
  await sendPhotos('T', 1, [good], 0, async () => ({ json: async () => (++calls < 2 ? { ok: false, error_code: 429, parameters: { retry_after: 0 } } : { ok: true }) }));
  assert.equal(calls, 2);
  let tries = 0;
  await assert.rejects(sendPhotos('T', 1, [good], 0, async () => { tries++; return { json: async () => ({ ok: false, error_code: 429, parameters: { retry_after: 0 } }) }; }), /sendPhoto: 429/);
  assert.equal(tries, 5);
  assert.equal(retryMs({ parameters: { retry_after: 999 } }), 30500);
});

import { generatedVideos } from './images.mjs';
test('generatedVideos only returns finished mp4 files from the video folder', () => {
  const dir = mkdtempSync(join(tmpdir(), 'vid-'));
  const good = join(dir, 'a.mp4'); writeFileSync(good, 'v'.repeat(2000));
  const rows = [call('image-gen_generate_video', 'completed', { ok: true, video_path: good }), call('image-gen_generate_video', 'completed', { ok: true, video_path: good }),
    call('image-gen_generate_video', 'completed', { ok: false, video_path: good }), call('image-gen_generate_video', 'error', { ok: true, video_path: good }),
    call('image-gen_generate_video', 'completed', { ok: true, video_path: '/etc/passwd' }), call('image-gen_generate_video', 'completed', { ok: true, video_path: join(dir, '..', 'x.mp4') })];
  assert.deepEqual(generatedVideos(rows, dir), [good]);
});

import { videoRetryMs, sendVideos } from './images.mjs';
test('videos wait the full flood-control time Telegram asks for, up to three minutes', () => {
  assert.equal(videoRetryMs({ parameters: { retry_after: 76 } }), 77000);
  assert.equal(videoRetryMs({ parameters: { retry_after: 900 } }), 181000);
});
test('sendVideos retries after a 429 and then succeeds', async () => {
  const file = join(mkdtempSync(join(tmpdir(), 'v-')), 'a.mp4'); writeFileSync(file, 'v'.repeat(2000));
  let n = 0;
  const realSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (fn) => realSetTimeout(fn, 0);
  try {
    await sendVideos('t', 1, [file], null, async () => ({ json: async () => (++n < 3 ? { ok: false, error_code: 429, parameters: { retry_after: 1 } } : { ok: true, result: { message_id: 7 } }) }));
  } finally { globalThis.setTimeout = realSetTimeout; }
  assert.equal(n, 3);
});

// ---- flood control and pacing (fake clock: the sleep function advances it, so nothing really waits)
const clock = () => { let t = 1_000_000; return { now: () => t, sleep: async ms => { t += ms; }, advance: ms => { t += ms; } }; };
test('sends a set with a gap between pictures, none before the first', async () => {
  resetFlood(); const c = clock(), gaps = [], at = [];
  await sendPhotos('T', 1, [good, good, good], 0, async () => { at.push(c.now()); return { json: async () => ({ ok: true }) }; }, { now: c.now, sleep: async ms => { gaps.push(ms); await c.sleep(ms); }, gapMs: 2000 });
  assert.deepEqual(gaps, [2000, 2000]); assert.equal(at.length, 3); assert.equal(at[1] - at[0], 2000);
});
test('a flood wait seen on one picture is honoured by the next one, in full', async () => {
  resetFlood(); const c = clock(); let calls = 0; const at = [];
  await sendPhotos('T', 1, [good, good], 0, async () => { at.push(c.now()); return { json: async () => (++calls === 1 ? { ok: false, error_code: 429, parameters: { retry_after: 60 } } : { ok: true }) }; }, { now: c.now, sleep: c.sleep, gapMs: 0 });
  assert.equal(calls, 3);                                         // picture 1 refused once, then sent; picture 2 sent
  assert.ok(at[1] - at[0] >= 60500, `waited ${at[1] - at[0]} ms, Telegram asked for 60 s`);   // not capped at 30 s
  assert.equal(floodMs({ parameters: { retry_after: 999 } }), 180500);
});
test('never sends while a flood wait recorded by an earlier call is still active', async () => {
  resetFlood(); const c = clock();
  await assert.rejects(sendPhotos('T', 1, [good], 0, async () => ({ json: async () => ({ ok: false, error_code: 429, parameters: { retry_after: 20 } }) }), { now: c.now, sleep: c.sleep, gapMs: 0 }), /sendPhoto: 429/);
  const endedAt = c.now(); let sentAt = 0;                        // the first set ended while still throttled; a different caller now tries to send
  await sendPhotos('T', 1, [good], 0, async () => { sentAt = c.now(); return { json: async () => ({ ok: true }) }; }, { now: c.now, sleep: c.sleep, gapMs: 0 });
  assert.ok(sentAt - endedAt >= 20500, `second send came ${sentAt - endedAt} ms after the flood was recorded, must wait the 20 s Telegram named`);
});
test('a picture that fails does not drop the rest; the error says how many were not sent', async () => {
  resetFlood(); const c = clock(); let n = 0;
  await assert.rejects(sendPhotos('T', 1, [good, good, good], 0, async () => ({ json: async () => (++n === 1 ? { ok: false, error_code: 400 } : { ok: true }) }), { now: c.now, sleep: c.sleep, gapMs: 0 }), /sendPhoto: 400 \(1 of 3 pictures not sent\)/);
  assert.equal(n, 3);                                             // all three were tried
});

test('one generate_image_set call can deliver several pictures (one text part each), in order, ignoring the summary part and anything outside the folder', () => {
  const files = [1, 2, 3].map(i => { const f = join(dir, `set-${i}.png`); writeFileSync(f, Buffer.alloc(500)); return f; });
  const row = { type: 'assistant', content: [{ type: 'tool', name: 'img-video_generate_image_set', state: { status: 'completed', content: [
    ...files.map((f, i) => ({ type: 'text', text: JSON.stringify({ ok: true, image_path: f, index: i + 1, topic: `t${i}` }) })),
    { type: 'text', text: JSON.stringify({ ok: true, did: 'Made 3 pictures' }) },
    { type: 'text', text: JSON.stringify({ ok: true, image_path: '/etc/passwd' }) }] } }] };
  assert.deepEqual(generatedImages([row], dir), files);
});

test('captions of a picture set are collected per file and sent with each photo', async () => {
  const files = [1, 2].map(i => { const f = join(dir, `cap-${i}.png`); writeFileSync(f, Buffer.alloc(500)); return f; });
  const row = { type: 'assistant', content: [{ type: 'tool', name: 'img-video_generate_image_set', state: { status: 'completed', content: [
    { type: 'text', text: JSON.stringify({ ok: true, image_path: files[0], index: 1, topic: 'White light', caption: 'Sunlight holds every colour.' }) },
    { type: 'text', text: JSON.stringify({ ok: true, image_path: files[1], index: 2, topic: 'Refraction', caption: 'x'.repeat(2000) }) },
    { type: 'text', text: JSON.stringify({ ok: true, image_path: '/etc/passwd', index: 3, topic: 'evil', caption: 'no' }) }] } }] };
  const caps = imageCaptions([row], dir);
  assert.equal(caps.size, 2); assert.equal(caps.get(files[0]), '1. White light\nSunlight holds every colour.'); assert.equal(caps.get(files[1]).length, '2. Refraction\n'.length + 1000);
  resetFlood(); const sent = [];
  await sendPhotos('T', 1, files, 0, async (url, init) => { sent.push(init.body.get('caption')); return { json: async () => ({ ok: true }) }; }, { gapMs: 0, captions: caps });
  assert.equal(sent[0], '1. White light\nSunlight holds every colour.'); assert.ok(sent[1].length <= 1024);
  const plain = []; await sendPhotos('T', 1, [good], 0, async (url, init) => { plain.push(init.body.get('caption')); return { json: async () => ({ ok: true }) }; }, { gapMs: 0 });
  assert.deepEqual(plain, [null]);                               // photos from other tools still go out without a caption
});


test('sendPhotos retries a stalled upload on a fresh connection instead of losing the picture', async () => {
  resetFlood();
  const sent = []; let calls = 0;
  const fetchImpl = async (url, init) => { calls++; if (calls === 1) { const e = new Error('The operation was aborted due to timeout'); e.name = 'TimeoutError'; throw e; } sent.push(init.body.get('chat_id')); return { json: async () => ({ ok: true, result: {} }) }; };
  await sendPhotos('T', 42, [good], 7, fetchImpl, { gapMs: 0, retryDelayMs: 0 });
  assert.deepEqual([calls, sent], [2, ['42']]);
});

test('sendPhotos gives up after a few stalls, says so, and still tries the other pictures', async () => {
  resetFlood();
  let calls = 0; const fetchImpl = async () => { calls++; const e = new Error('aborted'); e.name = 'TimeoutError'; throw e; };
  await assert.rejects(() => sendPhotos('T', 42, [good, good], 7, fetchImpl, { gapMs: 0, retryDelayMs: 0 }), /network: TimeoutError.*2 of 2 pictures not sent/s);
  assert.equal(calls, 8);                                                  // 4 attempts for each of the two pictures
});

test('sendPhotos and sendVideos return the ids of the messages they sent', async () => {
  const { mkdtempSync: mk, writeFileSync: wf } = await import('node:fs'); const { tmpdir: td } = await import('node:os'); const { join: j } = await import('node:path');
  const d = mk(j(td(), 'ids-')); const files = ['a.png', 'b.png'].map(n => { const f = j(d, n); wf(f, Buffer.alloc(100)); return f; }); const mp4 = j(d, 'v.mp4'); wf(mp4, Buffer.alloc(100));
  let n = 100; const fetchImpl = async () => ({ json: async () => ({ ok: true, result: { message_id: ++n } }) });
  const { sendVideos: sv } = await import('./images.mjs');
  assert.deepEqual(await sendPhotos('T', 1, files, 0, fetchImpl, { gapMs: 0 }), [101, 102]);
  assert.deepEqual(await sv('T', 1, [mp4], 0, fetchImpl), [103]);
});
