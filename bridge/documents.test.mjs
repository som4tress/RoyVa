import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, readdirSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { documentOf, saveInboxDocument, MAX_DOC_BYTES, telegramDocument } from './documents.mjs';

const dir = () => join(mkdtempSync(join(tmpdir(), 'docs-')), 'inbox');

test('documents are recognised by type or file name, pictures and videos are not documents', () => {
  const yes = [['application/pdf', 'a.pdf'], ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'a.docx'], ['application/msword', 'a.doc'],
    ['application/vnd.oasis.opendocument.text', 'a.odt'], ['application/vnd.oasis.opendocument.spreadsheet', 'a.ods'], ['application/vnd.oasis.opendocument.presentation', 'a.odp'],
    ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'a.xlsx'], ['application/vnd.openxmlformats-officedocument.presentationml.presentation', 'a.pptx'],
    ['text/plain', 'a.txt'], ['text/markdown', 'a.md'], ['text/csv', 'a.csv'], ['application/octet-stream', 'report.PDF'], [undefined, 'notes.docx']];
  for (const [mime_type, file_name] of yes) assert.ok(documentOf({ document: { file_id: 'x', file_size: 10, mime_type, file_name } }), `${mime_type} ${file_name}`);
  for (const [mime_type, file_name] of [['image/jpeg', 'a.jpg'], ['video/mp4', 'a.mp4'], ['application/zip', 'a.zip'], ['application/x-msdownload', 'a.exe']]) assert.equal(documentOf({ document: { file_id: 'x', mime_type, file_name } }), undefined, `${mime_type} ${file_name}`);
  assert.equal(documentOf({ text: 'hello' }), undefined); assert.equal(documentOf({ photo: [{ file_id: 'p' }] }), undefined);
});

test('the saved file keeps a safe version of its name and the prompt names the path', () => {
  const d = dir();
  const out = saveInboxDocument({ bytes: Buffer.from('%PDF'), name: 'Lease agreement (final).pdf' }, 'summarize this', d);
  const m = /^summarize this\n\n\[Attached document: (.+)\]$/.exec(out); assert.ok(m, out);
  assert.ok(m[1].startsWith(join(d, 'docs')) && m[1].endsWith('Lease_agreement_final_.pdf'), m[1]); assert.deepEqual(readFileSync(m[1]), Buffer.from('%PDF'));
});

test('a name cannot place the file outside the inbox', () => {
  const d = dir();
  for (const name of ['../../evil.pdf', '/etc/passwd', '..', '', 'a/b/c.pdf', '.hidden.pdf']) {
    const out = saveInboxDocument({ bytes: Buffer.from('x'), name }, 't', d); const p = /\[Attached document: (.+)\]/.exec(out)[1];
    assert.ok(p.startsWith(join(d, 'docs') + '/'), `${name} -> ${p}`); assert.ok(!p.slice(join(d, 'docs').length + 1).includes('/'), p); assert.ok(!p.split('/').at(-1).startsWith('.'), p);
  }
});

test('a message with no text still gets a useful request, a caption is kept', () => {
  const d = dir();
  assert.match(saveInboxDocument({ bytes: Buffer.from('x'), name: 'a.pdf' }, '', d), /^Read this document and tell me what it is about\.\n\n\[Attached document: /);
  assert.match(saveInboxDocument({ bytes: Buffer.from('x'), name: 'a.pdf' }, 'what is the total?', d), /^what is the total\?\n\n/);
});

test('only the newest 30 documents are kept, the pictures next to them are left alone', () => {
  const d = dir();
  for (let i = 0; i < 33; i++) saveInboxDocument({ bytes: Buffer.from('x'), name: `f${i}.txt` }, 't', d);
  assert.equal(readdirSync(join(d, 'docs')).length, 30);
});

test('a file over the limit is refused with a message, nothing is downloaded', async () => {
  let downloaded = false;
  const tg = async () => { downloaded = true; return { file_path: 'x' }; };
  await assert.rejects(() => telegramDocument({ document: { file_id: 'x', file_size: MAX_DOC_BYTES + 1, mime_type: 'application/pdf', file_name: 'big.pdf' } }, tg, 'T', dir()), /20 MB/);
  assert.equal(downloaded, false);
});

test('downloading saves the file and returns the prompt with its path', async () => {
  const d = dir(); const calls = [];
  const tg = async (method, args) => { calls.push([method, args]); return { file_path: 'documents/file_1.pdf' }; };
  const fetchFn = async url => { calls.push(['fetch', url]); return new Response(Buffer.from('%PDF-bytes')); };
  const out = await telegramDocument({ caption: 'summarize', document: { file_id: 'F1', file_size: 10, mime_type: 'application/pdf', file_name: 'r.pdf' } }, tg, 'TOKEN', d, fetchFn);
  assert.deepEqual(calls[0], ['getFile', { file_id: 'F1' }]); assert.match(calls[1][1], /botTOKEN\/documents\/file_1\.pdf/);
  const p = /\[Attached document: (.+)\]/.exec(out)[1]; assert.equal(readFileSync(p, 'utf8'), '%PDF-bytes'); assert.ok(existsSync(p)); assert.match(out, /^summarize\n\n/);
});
