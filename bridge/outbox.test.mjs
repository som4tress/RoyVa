import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { asyncJobs } from './images.mjs';
import { deliverOnce, registerJob } from './outbox.mjs';

const call = (name, status, payload) => ({ type: 'assistant', content: [{ type: 'tool', name, state: { status, content: [{ type: 'text', text: JSON.stringify(payload) }] } }] });

test('asyncJobs finds the background jobs a run started and ignores everything else', () => {
  const rows = [call('img-video_generate_image_set', 'completed', { ok: true, async_job: '20261117-120000-abc123', kind: 'set' }),
    call('img-video_generate_video', 'completed', { ok: true, async_job: '20261117-120001-def456', kind: 'video' }),
    call('img-video_generate_video', 'completed', { ok: true, async_job: '20261117-120001-def456', kind: 'video' }),              // a replayed row: counted once
    call('img-video_generate_image_set', 'completed', { ok: false, error: 'busy' }),
    call('img-video_generate_image_set', 'running', { ok: true, async_job: '20261117-120002-zzz999', kind: 'set' }),
    call('img-video_generate_image_set', 'completed', { ok: true, async_job: '../../etc/passwd', kind: 'set' }),                    // not a safe name
    call('img-video_generate_image', 'completed', { ok: true, async_job: '20261117-120003-nnn000' })];
  assert.deepEqual(asyncJobs(rows), [{ job: '20261117-120000-abc123', kind: 'set' }, { job: '20261117-120001-def456', kind: 'video' }]);
});

function setup() {
  const root = mkdtempSync(join(tmpdir(), 'outbox-')), dir = join(root, 'outbox'), imageDir = join(root, 'images'), videoDir = join(root, 'videos');
  for (const d of [dir, join(dir, 'done'), imageDir, videoDir]) mkdirSync(d, { recursive: true });
  const texts = [], photos = [], videos = [];
  const sendText = async (chatId, text, replyTo) => { texts.push({ chatId, text, replyTo }); };
  const fetchImpl = async (url, init) => {
    const method = url.split('/').pop(); const form = init.body; const chat = form.get('chat_id');
    if (method === 'sendPhoto') photos.push({ chat, caption: form.get('caption'), name: form.get('photo').name });
    if (method === 'sendVideo') videos.push({ chat, name: form.get('video').name });
    return { json: async () => ({ ok: true, result: {} }) };
  };
  const ctx = { dir, token: 'T', sendText, fetchImpl, imageDir, videoDir, sendOpts: { gapMs: 0 }, log: { error() {} } };
  const done = (job, payload) => writeFileSync(join(dir, 'done', `${job}.json`), JSON.stringify({ job, ...payload }));
  return { dir, imageDir, videoDir, texts, photos, videos, ctx, done, ls: d => existsSync(join(dir, d)) ? readdirSync(join(dir, d)) : [] };
}

test('a finished picture set is posted to the chat that asked, with captions, then a one-line message', async () => {
  const s = setup(); registerJob(s.dir, 'job-set-0001', { chatId: 42, replyTo: 7 });
  const files = [1, 2].map(i => { const f = join(s.imageDir, `imgset-x-0${i}.png`); writeFileSync(f, Buffer.alloc(2000)); return f; });
  s.done('job-set-0001', { ok: true, kind: 'images', title: 'GPU basics', images: files.map((path, k) => ({ path, index: k + 1, topic: `topic ${k + 1}`, caption: `caption ${k + 1}` })) });
  assert.deepEqual(await deliverOnce(s.ctx), { delivered: 1 });
  assert.deepEqual(s.photos.map(p => [p.chat, p.caption]), [['42', '1. topic 1\ncaption 1'], ['42', '2. topic 2\ncaption 2']]);
  assert.deepEqual(s.texts, [{ chatId: 42, text: 'Here are your 2 pictures: GPU basics.', replyTo: 7 }]);
  assert.deepEqual([s.ls('done'), s.ls('delivered'), s.ls('pending')], [[], ['job-set-0001.json'], []]);
  assert.deepEqual(await deliverOnce(s.ctx), { delivered: 0 });                      // nothing is posted twice
});

test('a finished video is posted to the chat that asked', async () => {
  const s = setup(); registerJob(s.dir, 'job-vid-0001', { chatId: 9, replyTo: 3 });
  const f = join(s.videoDir, 'video-x.mp4'); writeFileSync(f, Buffer.alloc(5000));
  s.done('job-vid-0001', { ok: true, kind: 'video', title: 'Rainbows', video: { path: f, seconds: 47 } });
  assert.deepEqual(await deliverOnce(s.ctx), { delivered: 1 });
  assert.deepEqual(s.videos, [{ chat: '9', name: 'video-x.mp4' }]); assert.equal(s.texts[0].text, 'Here is your video: Rainbows.');
});

test('a failed job tells the chat what went wrong', async () => {
  const s = setup(); registerJob(s.dir, 'job-bad-0001', { chatId: 5, replyTo: 1 });
  s.done('job-bad-0001', { ok: false, kind: 'video', error: 'the 3090 is not reachable' });
  await deliverOnce(s.ctx);
  assert.match(s.texts[0].text, /could not finish that video: the 3090 is not reachable/); assert.equal(s.photos.length + s.videos.length, 0);
});

test('a result whose chat is not known yet waits, and files outside the picture folder are never uploaded', async () => {
  const s = setup();
  s.done('job-new-0001', { ok: true, kind: 'images', images: [] });
  assert.deepEqual(await deliverOnce(s.ctx), { delivered: 0 }); assert.deepEqual(s.ls('done'), ['job-new-0001.json']);          // kept for later
  registerJob(s.dir, 'job-new-0001', { chatId: 1, replyTo: 1 });
  const outside = join(s.dir, 'secret.png'); writeFileSync(outside, Buffer.alloc(100));
  s.done('job-new-0001', { ok: true, kind: 'images', images: [{ path: outside, index: 1, topic: 't', caption: 'c' }] });
  for (let i = 0; i < 3; i++) await deliverOnce(s.ctx);                                // never sent; after the attempt limit it is parked as failed
  assert.equal(s.photos.length, 0); assert.deepEqual([s.ls('done'), s.ls('failed')], [[], ['job-new-0001.json']]);
});

test('an old result nobody claimed is parked, and a garbage file is set aside', async () => {
  const s = setup(); s.done('job-old-0001', { ok: true, kind: 'images', images: [] }); writeFileSync(join(s.dir, 'done', 'garbage.json'), 'not json');
  const old = new Date(Date.now() - 7 * 3600 * 1000); utimesSync(join(s.dir, 'done', 'job-old-0001.json'), old, old);
  await deliverOnce(s.ctx); assert.deepEqual([s.ls('orphaned'), s.ls('failed')], [['job-old-0001.json'], ['garbage.json']]);
});

test('the messages a finished video posts are reported with the conversation they belong to, so Forget can remove them', async () => {
  const s = setup(); registerJob(s.dir, 'job-vid-0099', { chatId: 42, replyTo: 7, kind: 'video', sessionID: 'ses_Z' });
  const f = join(s.videoDir, 'v.mp4'); writeFileSync(f, Buffer.alloc(2000)); s.done('job-vid-0099', { ok: true, kind: 'video', video: { path: f }, title: 'T' });
  let id = 500; const sent = [];
  s.ctx.fetchImpl = async () => ({ json: async () => ({ ok: true, result: { message_id: ++id } }) });
  s.ctx.sendText = async () => ({ message_id: ++id });
  s.ctx.onSent = (chatId, ids, sessionID) => sent.push({ chatId, ids, sessionID });
  await deliverOnce(s.ctx);
  assert.deepEqual(sent.flatMap(x => x.ids).sort(), [501, 502]); assert.ok(sent.every(x => x.chatId === 42 && x.sessionID === 'ses_Z'));
});
