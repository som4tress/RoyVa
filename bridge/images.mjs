import { readFileSync, existsSync, statSync } from 'node:fs';
import { resolve, sep, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

// Pictures made by the image tool are the only files the bridge will ever upload, and only from this folder.
export const IMAGE_DIR = process.env.ROYVA_IMAGE_DIR || fileURLToPath(new URL('../runtime/data/images', import.meta.url));
export const VIDEO_DIR = process.env.ROYVA_VIDEO_DIR || fileURLToPath(new URL('../runtime/data/videos', import.meta.url));
const MAX_BYTES = 10 * 1024 * 1024;   // Telegram's sendPhoto limit
const MAX_VIDEO_BYTES = 50 * 1024 * 1024;   // Telegram's sendVideo limit for bots

const resultTexts = part => {
  const raw = part.state?.content;
  const items = typeof raw === 'string' ? (() => { try { return JSON.parse(raw); } catch { return []; } })() : raw;
  return (Array.isArray(items) ? items : []).filter(item => item?.type === 'text').map(item => item.text);
};

// Image files named by completed generate_image calls in a run, in order, without duplicates; anything outside IMAGE_DIR is ignored.
export function generatedImages(rows, dir = IMAGE_DIR) {
  const base = resolve(dir) + sep, out = [];
  for (const row of rows) {
    if (row.type !== 'assistant') continue;
    for (const part of row.content || []) {
      if (part.type !== 'tool' || !/(generate|edit)_image(_set)?$/.test(part.name || '') || part.state?.status !== 'completed') continue;
      for (const text of resultTexts(part)) {
        let value; try { value = JSON.parse(text); } catch { continue; }
        const file = value?.ok === true && typeof value.image_path === 'string' ? resolve(value.image_path) : '';
        if (file.startsWith(base) && file.endsWith('.png') && existsSync(file) && statSync(file).size <= MAX_BYTES && !out.includes(file)) out.push(file);
      }
    }
  }
  return out;
}

// Captions the image-set tool supplied with its pictures, keyed by file: "<n>. <topic>" on the first line and the caption under it (Telegram allows 1024 characters; we keep 1000).
export function imageCaptions(rows, dir = IMAGE_DIR) {
  const base = resolve(dir) + sep, out = new Map();
  for (const row of rows) {
    if (row.type !== 'assistant') continue;
    for (const part of row.content || []) {
      if (part.type !== 'tool' || !/generate_image_set$/.test(part.name || '') || part.state?.status !== 'completed') continue;
      for (const text of resultTexts(part)) {
        let value; try { value = JSON.parse(text); } catch { continue; }
        const file = value?.ok === true && typeof value.image_path === 'string' ? resolve(value.image_path) : '';
        if (!file.startsWith(base) || typeof value.caption !== 'string' || !value.caption.trim()) continue;
        const head = [Number.isInteger(value.index) ? `${value.index}.` : '', typeof value.topic === 'string' ? value.topic.trim() : ''].filter(Boolean).join(' ');
        out.set(file, (head ? head + '\n' : '') + value.caption.trim().slice(0, 1000));
      }
    }
  }
  return out;
}

// Video files named by completed generate_video calls in a run (same rules as pictures: only from VIDEO_DIR, .mp4, size-limited, no duplicates).
export function generatedVideos(rows, dir = VIDEO_DIR) {
  const base = resolve(dir) + sep, out = [];
  for (const row of rows) {
    if (row.type !== 'assistant') continue;
    for (const part of row.content || []) {
      if (part.type !== 'tool' || !/generate_video$/.test(part.name || '') || part.state?.status !== 'completed') continue;
      for (const text of resultTexts(part)) {
        let value; try { value = JSON.parse(text); } catch { continue; }
        const file = value?.ok === true && typeof value.video_path === 'string' ? resolve(value.video_path) : '';
        if (file.startsWith(base) && file.endsWith('.mp4') && existsSync(file) && statSync(file).size <= MAX_VIDEO_BYTES && !out.includes(file)) out.push(file);
      }
    }
  }
  return out;
}

// Background jobs a run started (picture sets and videos return at once): [{job, kind}] from completed tool rows whose result carries `async_job`. The bridge then remembers which chat asked and posts the result when it is ready.
export function asyncJobs(rows) {
  const out = [];
  for (const row of rows) {
    if (row.type !== 'assistant') continue;
    for (const part of row.content || []) {
      if (part.type !== 'tool' || !/generate_(image_set|video)$/.test(part.name || '') || part.state?.status !== 'completed') continue;
      for (const text of resultTexts(part)) {
        let value; try { value = JSON.parse(text); } catch { continue; }
        if (value?.ok === true && typeof value.async_job === 'string' && /^[\w-]{6,64}$/.test(value.async_job) && !out.some(j => j.job === value.async_job)) out.push({ job: value.async_job, kind: value.kind === 'video' ? 'video' : 'set' });
      }
    }
  }
  return out;
}

// Cost of each picture the tool reported (render seconds, tokens the text encoder read), keyed by file so a replayed session is never counted twice.
export function imageRuns(rows) {
  const out = [];
  for (const row of rows) {
    if (row.type !== 'assistant') continue;
    for (const part of row.content || []) {
      if (part.type !== 'tool' || !/(generate|edit)_image(_set)?$/.test(part.name || '') || part.state?.status !== 'completed') continue;
      for (const text of resultTexts(part)) {
        let value; try { value = JSON.parse(text); } catch { continue; }
        if (value?.ok === true && typeof value.image_path === 'string') out.push({ file: value.image_path, secs: Number(value.secs) || 0, tokens: Number(value.encoder_tokens) || 0 });
      }
    }
  }
  return out;
}

export const videoRetryMs = result => Math.min(180, Number(result.parameters?.retry_after ?? 5)) * 1000 + 1000;
export const retryMs = result => Math.min(30, Number(result.parameters?.retry_after ?? 5)) * 1000 + 500;
// Telegram flood control. After a 429, every send in this process must wait until the time Telegram named; the state is shared, so a later picture never walks into the same limit.
// Telegram offers no way to ask "am I throttled?", so the only honest check is this record: it is consulted before EVERY send, including retries.
const flood = { until: 0 };
export const resetFlood = () => { flood.until = 0; };
export const floodMs = result => Math.min(180, Number(result.parameters?.retry_after ?? 5)) * 1000 + 500;   // honours the full wait (up to 3 minutes), unlike retryMs
const realSleep = ms => new Promise(done => setTimeout(done, ms));
// Pictures are sent one at a time with a gap between them (ROYVA_PHOTO_GAP_MS, default 2000) so a set of ten does not arrive as a burst. A picture that cannot be sent no longer drops the rest:
// the others are still tried, and the error at the end says how many failed. `opts.captions` (a Map file -> text) puts a caption on each picture. `opts.sleep`, `opts.now` and `opts.gapMs` exist so tests do not have to wait.
export async function sendPhotos(token, chatId, files, replyTo, fetchImpl = fetch, opts = {}) {
  const sleep = opts.sleep || realSleep, now = opts.now || Date.now;
  const gap = opts.gapMs ?? Number(process.env.ROYVA_PHOTO_GAP_MS ?? 2000);
  let failed = 0, lastCode = 0; const ids = [];
  for (let i = 0; i < files.length; i++) {
    if (i > 0 && gap > 0) await sleep(gap);
    const form = new FormData();
    form.set('chat_id', String(chatId));
    if (replyTo) form.set('reply_parameters', JSON.stringify({ message_id: replyTo, allow_sending_without_reply: true }));
    form.set('photo', new Blob([readFileSync(files[i])], { type: 'image/png' }), basename(files[i]));
    const caption = opts.captions?.get(resolve(files[i])); if (caption) form.set('caption', caption.slice(0, 1000));
    let sent = false;
    for (let attempt = 0; attempt < 5; attempt++) {
      const wait = flood.until - now();
      if (wait > 0) await sleep(wait);                                       // a flood wait is active: do not send into it
      let result;
      try {
        const response = await fetchImpl(`https://api.telegram.org/bot${token}/sendPhoto`, { method: 'POST', body: form, signal: AbortSignal.timeout(opts.timeoutMs ?? 40000) });
        result = await response.json();
      } catch (error) {                                                    // a stalled or dropped connection (2026-11-17: one upload hung for 65 s and the picture was lost): try again on a fresh connection
        lastCode = `network: ${error.name}`;
        if (attempt < 3) { await sleep(opts.retryDelayMs ?? 2000); continue; }
        break;
      }
      if (result.ok) { sent = true; if (result.result?.message_id) ids.push(result.result.message_id); break; }
      lastCode = result.error_code;
      if (result.error_code === 429) { flood.until = Math.max(flood.until, now() + floodMs(result)); continue; }
      break;
    }
    if (!sent) failed++;
  }
  if (failed) throw new Error(`Telegram sendPhoto: ${lastCode}` + (files.length > 1 ? ` (${failed} of ${files.length} pictures not sent)` : ''));
  return ids;                                                                  // the ids of the messages sent, so Forget this chat can remove them
}

export async function sendVideos(token, chatId, files, replyTo, fetchImpl = fetch) {
  const ids = [];
  for (const file of files) {
    const form = new FormData();
    form.set('chat_id', String(chatId));
    form.set('supports_streaming', 'true');
    if (replyTo) form.set('reply_parameters', JSON.stringify({ message_id: replyTo, allow_sending_without_reply: true }));
    form.set('video', new Blob([readFileSync(file)], { type: 'video/mp4' }), basename(file));
    for (let attempt = 0; ; attempt++) {
      let result;
      try {
        const response = await fetchImpl(`https://api.telegram.org/bot${token}/sendVideo`, { method: 'POST', body: form, signal: AbortSignal.timeout(120000) });
        result = await response.json();
      } catch (error) {                                                    // a stalled or dropped connection: one more try on a fresh connection
        if (attempt < 2) { await new Promise(done => setTimeout(done, 2000)); continue; }
        throw new Error(`Telegram sendVideo: network ${error.name}`);
      }
      // Telegram says exactly how long to wait; retrying sooner is refused again and prolongs the wait, so honour the full time (a video is worth waiting for).
      if (!result.ok && result.error_code === 429 && attempt < 6) { await new Promise(done => setTimeout(done, videoRetryMs(result))); continue; }
      if (!result.ok) throw new Error(`Telegram sendVideo: ${result.error_code}`);
      if (result.result?.message_id) ids.push(result.result.message_id);
      console.log(`Sent video ${basename(file)} to chat (message ${result.result?.message_id}${attempt ? `, after ${attempt} flood-control wait(s)` : ''})`);
      break;
    }
  }
  return ids;
}

// Send a text file (e.g. the full call of an approval request) as a Telegram document. Throws if it could not be sent.
export async function sendDocument(token, chatId, name, content, replyTo, fetchImpl = fetch) {
  const form = new FormData();
  form.set('chat_id', String(chatId));
  if (replyTo) form.set('reply_parameters', JSON.stringify({ message_id: replyTo, allow_sending_without_reply: true }));
  form.set('document', new Blob([content], { type: 'application/json' }), name);
  for (let attempt = 0; ; attempt++) {
    const response = await fetchImpl(`https://api.telegram.org/bot${token}/sendDocument`, { method: 'POST', body: form, signal: AbortSignal.timeout(65000) });
    const result = await response.json();
    if (!result.ok && result.error_code === 429 && attempt < 4) { await new Promise(done => setTimeout(done, retryMs(result))); continue; }
    if (!result.ok) throw new Error(`Telegram sendDocument: ${result.error_code}`);
    return result.result;
  }
}
