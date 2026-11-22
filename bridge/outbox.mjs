import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { IMAGE_DIR, VIDEO_DIR, sendPhotos, sendVideos } from './images.mjs';

// Picture sets and videos are made in the background (mcp/img_video/runner.py leaves <job>.json in done/ when finished). The bridge remembers which chat asked (pending/<job>.json, written when the run that started
// the job ends) and posts the result there. Only files inside the picture / video folders are ever uploaded, exactly as for pictures made while you wait.
export const OUTBOX_DIR = process.env.ROYVA_OUTBOX_DIR || fileURLToPath(new URL('../runtime/data/outbox', import.meta.url));
const MAX_ATTEMPTS = 3, ORPHAN_MS = 6 * 3600 * 1000, MAX_VIDEO_BYTES = 50 * 1024 * 1024;
const safeName = job => /^[\w-]{6,64}$/.test(job);
const readJson = file => { try { return JSON.parse(readFileSync(file, 'utf8')); } catch { return null; } };
const inside = (file, dir) => resolve(file).startsWith(resolve(dir) + sep);
const moveTo = (dir, folder, file, name) => { mkdirSync(join(dir, folder), { recursive: true }); renameSync(file, join(dir, folder, name)); };

export function registerJob(dir, job, target) {
  if (!safeName(job)) return false;
  mkdirSync(join(dir, 'pending'), { recursive: true });
  writeFileSync(join(dir, 'pending', `${job}.json`), JSON.stringify({ job, chatId: target.chatId, replyTo: target.replyTo, statusMessageId: target.statusMessageId, sessionID: target.sessionID, startedAt: target.startedAt ?? Date.now(), kind: target.kind === 'video' ? 'video' : 'set', createdAt: Date.now(), attempts: 0 }));
  return true;
}

// ---- the live progress bar for a background job: the status message of the request that started it keeps being edited every few seconds, with real stages from the agent's progress file, until the result arrives.
export const requestCancel = (dir, job) => { if (!safeName(job)) return false; mkdirSync(join(dir, 'cancel'), { recursive: true }); writeFileSync(join(dir, 'cancel', job), '1'); return true; };   // the runner polls this file and stops the agent
const isCancelling = (dir, job) => existsSync(join(dir, 'cancel', job));
export const formatElapsed = s => s >= 60 ? `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s` : `${s}s`;

// What the agent is doing, from its progress file ({stages: {name: running|done}, shots_done/total, pictures_done/total}).
export function progressLabel(p = {}, kind = 'set') {
  const st = p.stages || {}, running = name => st[name] === 'running', shots = p.shots_total ? `${p.shots_done || 0}/${p.shots_total}` : '', pics = p.pictures_total ? `${p.pictures_done || 0}/${p.pictures_total}` : '';
  if (running('video')) return 'Assembling the video';
  if (running('clips') || running('voice')) return `Animating the clips${running('voice') ? ' · recording the voice-over' : ''}`;
  if (running('storyboard')) return 'Preparing the storyboard';
  if (running('direct') && running('images')) return `Director ${shots || 'planning'} · pictures ${pics || 'waiting'}`;
  if (running('images')) return `Drawing pictures ${pics}`.trim();
  if (running('direct')) return shots ? `Director writing shots ${shots}` : 'Director planning';
  if (running('research')) return 'Researching the web';
  if (running('plan')) return 'Planning';
  if (st.images === 'done' && kind === 'video') return 'Preparing the animation';
  return 'Starting';
}

export function statusText({ progress, kind, startedAt, now, cancelling = false }) {
  const elapsed = Math.max(0, Math.round((now - startedAt) / 1000)), blocks = Math.min(60, Math.max(1, Math.ceil(elapsed / 3))), hourglass = Math.floor(elapsed / 3) % 2 ? '⌛' : '⏳';
  return [`${cancelling ? '⏹ Stopping' : `${hourglass} Making your ${kind === 'video' ? 'video' : 'pictures'}`} · ${formatElapsed(elapsed)} elapsed`, `${'▰'.repeat(blocks)} · ${elapsed}s`, 'Each block ≈ 3s',
    cancelling ? 'Waiting for the GPU to stop' : progressLabel(progress, kind), ...(cancelling ? [] : ['Tap Stop to cancel'])].join('\n');
}

export function finalText(done, pending, now) {
  const elapsed = formatElapsed(Math.max(0, Math.round((now - (pending.startedAt || pending.createdAt)) / 1000)));
  if (done.cancelled) return `⏹ Stopped after ${elapsed}`;
  if (!done.ok) return `✗ Failed after ${elapsed}: ${String(done.error || 'something went wrong').slice(0, 200)}`;
  return `✓ Finished · ${elapsed}`;
}

const lastStatus = new Map(), finalized = new Set();
export async function updateStatuses({ dir = OUTBOX_DIR, editStatus, now = Date.now } = {}) {
  const pend = join(dir, 'pending'); let edited = 0;
  if (!editStatus || !existsSync(pend)) return edited;
  for (const name of readdirSync(pend).filter(n => n.endsWith('.json'))) {
    const job = name.slice(0, -5), p = readJson(join(pend, name));
    if (!p?.statusMessageId || !safeName(job) || existsSync(join(dir, 'done', name))) continue;                 // a finished job gets its last line from deliverOnce
    const text = statusText({ progress: readJson(join(dir, 'progress', `${job}.json`)) || {}, kind: p.kind, startedAt: p.startedAt || p.createdAt, now: now(), cancelling: isCancelling(dir, job) });
    if (lastStatus.get(job) === text) continue;
    lastStatus.set(job, text);
    try { await editStatus(p.chatId, p.statusMessageId, text, { stop: job }); edited++; } catch { /* the bar is a courtesy: never block the job */ }
  }
  return edited;
}

async function post(done, to, ctx) {
  const { token, sendText, fetchImpl, imageDir, videoDir, sendOpts } = ctx;
  const report = ids => { try { ctx.onSent?.(to.chatId, ids, to.sessionID); } catch { /* bookkeeping for Forget: never blocks a delivery */ } };       // the messages posted for this conversation
  const say = async text => { const r = await sendText(to.chatId, text, to.replyTo); report([r?.message_id]); };
  const title = done.title ? `: ${String(done.title).slice(0, 120)}` : '';
  if (to.statusMessageId && ctx.editStatus && !finalized.has(to.job)) {                                         // the live bar ends with its last line before the results arrive
    finalized.add(to.job); lastStatus.delete(to.job);
    try { await ctx.editStatus(to.chatId, to.statusMessageId, finalText(done, to, (ctx.now || Date.now)()), {}); } catch { /* courtesy */ }
  }
  if (done.cancelled) return;
  if (!done.ok) { await say(`Sorry, I could not finish that ${done.kind === 'video' ? 'video' : 'picture set'}: ${String(done.error || 'something went wrong').slice(0, 300)}`); return; }
  if (done.kind === 'video') {
    const file = done.video?.path ? resolve(done.video.path) : '';
    if (!file || !inside(file, videoDir) || !file.endsWith('.mp4') || !existsSync(file)) throw new Error('the finished video is not a sendable file');
    if (statSync(file).size > MAX_VIDEO_BYTES) { await say(`Your video is ready but too large for Telegram (${(statSync(file).size / 1e6).toFixed(0)} MB, the limit is 50 MB).`); return; }
    report(await sendVideos(token, to.chatId, [file], to.replyTo, fetchImpl));
    await say(`Here is your video${title}.`);
    return;
  }
  const images = (done.images || []).filter(i => typeof i?.path === 'string'), files = images.map(i => resolve(i.path)).filter(f => inside(f, imageDir) && f.endsWith('.png') && existsSync(f));
  if (!files.length) throw new Error('no sendable pictures');
  const captions = new Map(images.filter(i => files.includes(resolve(i.path)) && typeof i.caption === 'string' && i.caption.trim())
    .map(i => [resolve(i.path), ([Number.isInteger(i.index) ? `${i.index}.` : '', typeof i.topic === 'string' ? i.topic.trim() : ''].filter(Boolean).join(' ') + '\n' + i.caption.trim()).trim().slice(0, 1000)]));
  report(await sendPhotos(token, to.chatId, files, to.replyTo, fetchImpl, { ...sendOpts, captions }));
  try { const each = (Number(done.stage_seconds?.images) || 0) / files.length; ctx.onImages?.(files.map(file => ({ file, secs: each, tokens: 0 }))); } catch { /* usage numbers are a courtesy */ }       // image usage for background sets (the run itself never saw the pictures)
  await say(`Here are your ${files.length} pictures${title}.`);
}

// One pass over the outbox: post every finished job whose chat is known; leave the rest for the next pass.
export async function deliverOnce({ dir = OUTBOX_DIR, token, sendText, editStatus, onImages, onSent, fetchImpl = fetch, imageDir = IMAGE_DIR, videoDir = VIDEO_DIR, sendOpts = {}, now = Date.now, log = console } = {}) {
  const doneDir = join(dir, 'done'); let delivered = 0;
  if (!existsSync(doneDir)) return { delivered };
  for (const name of readdirSync(doneDir).filter(n => n.endsWith('.json') && !n.startsWith('.'))) {
    const file = join(doneDir, name), job = name.slice(0, -5), done = readJson(file);
    if (!done || !safeName(job)) { moveTo(dir, 'failed', file, name); continue; }
    const pendingFile = join(dir, 'pending', `${job}.json`), pending = readJson(pendingFile);
    if (!pending) { if (now() - statSync(file).mtimeMs > ORPHAN_MS) moveTo(dir, 'orphaned', file, name); continue; }     // no chat is known for it (yet): keep it
    try {
      await post(done, pending, { token, sendText, editStatus, onImages, onSent, fetchImpl, imageDir, videoDir, sendOpts, now });
      moveTo(dir, 'delivered', file, name); rmSync(pendingFile, { force: true }); delivered++;
    } catch (error) {
      log.error?.(`Could not post background job ${job}: ${error.message}`);
      pending.attempts = (pending.attempts || 0) + 1;
      if (pending.attempts >= MAX_ATTEMPTS) { moveTo(dir, 'failed', file, name); rmSync(pendingFile, { force: true }); } else writeFileSync(pendingFile, JSON.stringify(pending));
    }
  }
  return { delivered };
}

export function startOutboxWatcher(opts, intervalMs = 3000) {
  let busy = false;
  const timer = setInterval(async () => { if (busy) return; busy = true; try { await updateStatuses(opts); await deliverOnce(opts); } catch (error) { (opts.log || console).error?.(`Outbox pass failed: ${error.message}`); } finally { busy = false; } }, intervalMs);
  timer.unref?.();
  return () => clearInterval(timer);
}
