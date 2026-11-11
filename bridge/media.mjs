import {boundedDownload, MAX_BYTES, preparePrompt as expandVideos} from '../media-input/index.js';
export function attachment(message) {
  if (message.photo?.length) return {...message.photo.at(-1),mime:'image/jpeg',name:'photo.jpg'};
  if (message.video || message.video_note) return {...(message.video || message.video_note),mime:message.video?.mime_type || 'video/mp4',name:message.video?.file_name || 'video.mp4'};
  const doc=message.document;
  if (doc && /^(image|video)\//.test(doc.mime_type || '')) return {...doc,mime:doc.mime_type,name:doc.file_name || (/^video\//.test(doc.mime_type)?'video.mp4':'image.jpg')};
}
export async function telegramMedia(message,tg,token) {
  const media=attachment(message);if (!media) return [];
  if (media.file_size>MAX_BYTES || media.duration>600) throw Error('Photo/video limit: 20 MB; videos up to 10 minutes.');
  const file=await tg('getFile',{file_id:media.file_id});
  const data=await boundedDownload(await fetch(`https://api.telegram.org/file/bot${token}/${file.file_path}`,{signal:AbortSignal.timeout(60000)}));
  return [{uri:`data:${media.mime};base64,${data.toString('base64')}`,name:media.name}];
}
// Vanilla OpenCode does not load the media-input plugin, so videos are turned into sampled frames here, before the prompt is sent.
export async function withVideoFrames(files, text) {
  if (!files.some(f => /^data:video\//i.test(f.uri))) return {files, text};
  const event = {prompt: {files: [...files], text}, metadata: {}};
  await expandVideos(event);
  return {files: event.prompt.files, text: event.prompt.text};
}
// Photos sent in chat are also saved to runtime/data/inbox so the image-edit tool can read them; the prompt names the saved path.
import { mkdirSync, writeFileSync, readdirSync, statSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { randomBytes } from 'node:crypto';
import { fileURLToPath } from 'node:url';
export const INBOX_DIR = process.env.ROYVA_INBOX_DIR || fileURLToPath(new URL('../runtime/data/inbox', import.meta.url));
const KEEP_INBOX = 30;
export function saveInboxImages(files, text, dir = INBOX_DIR) {
  const lines = [];
  for (const file of files) {
    const match = /^data:image\/(jpeg|jpg|png);base64,(.+)$/s.exec(file.uri || '');
    if (!match) continue;
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    const path = join(dir, `${new Date().toISOString().replace(/[:.]/g, '-')}-${randomBytes(2).toString('hex')}.${match[1] === 'png' ? 'png' : 'jpg'}`);
    writeFileSync(path, Buffer.from(match[2], 'base64'), { mode: 0o600 });
    lines.push(`[Attached photo: ${path}]`);
  }
  if (lines.length) {
    const old = readdirSync(dir).map(n => join(dir, n)).sort((a, b) => statSync(a).mtimeMs - statSync(b).mtimeMs);
    for (const path of old.slice(0, Math.max(0, old.length - KEEP_INBOX))) try { unlinkSync(path); } catch {}
  }
  return lines.length ? `${text}\n\n${lines.join('\n')}` : text;
}
