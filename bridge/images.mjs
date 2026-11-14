import { readFileSync, existsSync, statSync } from 'node:fs';
import { resolve, sep, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

// Pictures made by the image tool are the only files the bridge will ever upload, and only from this folder.
export const IMAGE_DIR = process.env.ROYVA_IMAGE_DIR || fileURLToPath(new URL('../runtime/data/images', import.meta.url));
const MAX_BYTES = 10 * 1024 * 1024;   // Telegram's sendPhoto limit

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
      if (part.type !== 'tool' || !/(generate|edit)_image$/.test(part.name || '') || part.state?.status !== 'completed') continue;
      for (const text of resultTexts(part)) {
        let value; try { value = JSON.parse(text); } catch { continue; }
        const file = value?.ok === true && typeof value.image_path === 'string' ? resolve(value.image_path) : '';
        if (file.startsWith(base) && file.endsWith('.png') && existsSync(file) && statSync(file).size <= MAX_BYTES && !out.includes(file)) out.push(file);
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
      if (part.type !== 'tool' || !/(generate|edit)_image$/.test(part.name || '') || part.state?.status !== 'completed') continue;
      for (const text of resultTexts(part)) {
        let value; try { value = JSON.parse(text); } catch { continue; }
        if (value?.ok === true && typeof value.image_path === 'string') out.push({ file: value.image_path, secs: Number(value.secs) || 0, tokens: Number(value.encoder_tokens) || 0 });
      }
    }
  }
  return out;
}

export const retryMs = result => Math.min(30, Number(result.parameters?.retry_after ?? 5)) * 1000 + 500;
export async function sendPhotos(token, chatId, files, replyTo, fetchImpl = fetch) {
  for (const file of files) {
    const form = new FormData();
    form.set('chat_id', String(chatId));
    if (replyTo) form.set('reply_parameters', JSON.stringify({ message_id: replyTo, allow_sending_without_reply: true }));
    form.set('photo', new Blob([readFileSync(file)], { type: 'image/png' }), basename(file));
    for (let attempt = 0; ; attempt++) {
      const response = await fetchImpl(`https://api.telegram.org/bot${token}/sendPhoto`, { method: 'POST', body: form, signal: AbortSignal.timeout(65000) });
      const result = await response.json();
      if (!result.ok && result.error_code === 429 && attempt < 4) { await new Promise(done => setTimeout(done, retryMs(result))); continue; }
      if (!result.ok) throw new Error(`Telegram sendPhoto: ${result.error_code}`);
      break;
    }
  }
}

// Send a text file (e.g. the full call of an approval request) as a Telegram document. Throws if it could not be sent.
export async function sendDocument(token, chatId, name, content, replyTo, fetchImpl = fetch) {
  const form = new FormData();
  form.set('chat_id', String(chatId));
  if (replyTo) form.set('reply_parameters', JSON.stringify({ message_id: replyTo, allow_sending_without_reply: true }));
  form.set('document', new Blob([content], { type: 'application/json' }), name);
  const response = await fetchImpl(`https://api.telegram.org/bot${token}/sendDocument`, { method: 'POST', body: form, signal: AbortSignal.timeout(65000) });
  const result = await response.json();
  if (!result.ok) throw new Error(`Telegram sendDocument: ${result.error_code}`);
  return result.result;
}
