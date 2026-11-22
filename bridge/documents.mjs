// Documents sent in chat (PDF, Word, OpenDocument, Excel, PowerPoint, text): saved to runtime/data/inbox/docs and named in the prompt as "[Attached document: <path>]",
// the same way photos are. The document reader (mcp/docs) reads only from that folder.
import { mkdirSync, writeFileSync, readdirSync, statSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { randomBytes } from 'node:crypto';
import { INBOX_DIR } from './media.mjs';

export const MAX_DOC_BYTES = 20 * 1024 * 1024;               // Telegram's own download limit for bots
const KEEP_DOCS = 30;
export const MAX_TOTAL_BYTES = 30 * 1024 * 1024;       // all documents of one message together
const EXT = /\.(pdf|docx?|odt|ods|odp|xlsx?|pptx?|txt|md|markdown|csv|html?|rtf)$/i;
const MIME = /^(application\/pdf|application\/msword|application\/rtf|application\/vnd\.(openxmlformats-officedocument\.(wordprocessingml|spreadsheetml|presentationml)\.[a-z]+|oasis\.opendocument\.(text|spreadsheet|presentation)|ms-(excel|powerpoint))|text\/(plain|markdown|csv|html|rtf))$/i;

export function documentOf(message) {
  const doc = message.document;
  if (!doc || /^(image|video)\//.test(doc.mime_type || '')) return undefined;
  if (!(MIME.test(doc.mime_type || '') || EXT.test(doc.file_name || ''))) return undefined;
  return { ...doc, name: doc.file_name || 'document' };
}

const safeName = name => {
  const last = String(name || '').split(/[\\/]/).at(-1);
  const clean = last.replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^[._]+/, '').slice(-80);
  return clean && clean !== '.' ? clean : 'document';
};

const note = (text, lines) => `${String(text || '').trim() || 'Read this document and tell me what it is about.'}\n\n${lines.join('\n')}`;

function saveFile({ bytes, name }, dir) {
  const docs = join(dir, 'docs'); mkdirSync(docs, { recursive: true, mode: 0o700 });
  const path = join(docs, `${new Date().toISOString().replace(/[:.]/g, '-')}-${randomBytes(2).toString('hex')}-${safeName(name)}`);
  writeFileSync(path, bytes, { mode: 0o600 });
  const old = readdirSync(docs).map(n => join(docs, n)).sort((a, b) => statSync(a).mtimeMs - statSync(b).mtimeMs || (a < b ? -1 : 1));
  for (const p of old.slice(0, Math.max(0, old.length - KEEP_DOCS))) try { unlinkSync(p); } catch {}
  return path;
}

export function saveInboxDocument(file, text, dir = INBOX_DIR) {
  return note(text, [`[Attached document: ${saveFile(file, dir)}]`]);
}

// Returns the prompt (caption + one attached-document line per file), or null when the message has no readable document. Throws a message the user can read.
// Several files sent together arrive as an album (message._album): every file is saved, in the order sent; one that cannot be read is named as not read.
export async function telegramDocument(message, tg, token, dir = INBOX_DIR, fetchFn = fetch) {
  const parts = message._album || [message];
  const docs = parts.map(documentOf).filter(Boolean);
  if (!docs.length) return null;
  if (docs.some(d => d.file_size > MAX_DOC_BYTES)) throw new Error('Document limit: 20 MB per file.');
  if (docs.reduce((n, d) => n + (d.file_size || 0), 0) > MAX_TOTAL_BYTES) throw new Error('Document limit: 30 MB in total per message.');
  const lines = [];
  for (const doc of docs) {
    const file = await tg('getFile', { file_id: doc.file_id });
    const response = await fetchFn(`https://api.telegram.org/file/bot${token}/${file.file_path}`, { signal: AbortSignal.timeout(60000) });
    if (!response.ok) throw new Error('Document download failed.');
    const bytes = Buffer.from(await response.arrayBuffer());
    if (bytes.length > MAX_DOC_BYTES) throw new Error('Document limit: 20 MB per file.');
    lines.push(`[Attached document: ${saveFile({ bytes, name: doc.name }, dir)}]`);
  }
  for (const p of parts) if (p.document && !/^(image|video)\//.test(p.document.mime_type || '') && !documentOf(p)) lines.push(`[Not read: ${safeName(p.document.file_name)} (this kind of file cannot be read)]`);
  return note(message.caption || message.text, lines);
}
