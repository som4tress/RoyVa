import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { saveInboxImages } from './media.mjs';

const dir = () => join(mkdtempSync(join(tmpdir(), 'inbox-')), 'in');
const jpg = Buffer.from('fakejpegbytes');
test('saves a photo and names the path in the prompt', () => {
  const d = dir();
  const out = saveInboxImages([{ uri: `data:image/jpeg;base64,${jpg.toString('base64')}`, name: 'photo.jpg' }], 'make it ghibli', d);
  const m = /^make it ghibli\n\n\[Attached photo: (.+\.jpg)\]$/.exec(out);
  assert.ok(m, out); assert.deepEqual(readFileSync(m[1]), jpg); assert.ok(m[1].startsWith(d));
});
test('leaves the prompt alone for text only, videos and non-image data', () => {
  const d = dir();
  assert.equal(saveInboxImages([], 'hello', d), 'hello');
  assert.equal(saveInboxImages([{ uri: 'data:video/mp4;base64,AAAA' }, { uri: 'data:image/svg+xml;base64,AAAA' }], 'hi', d), 'hi');
});
test('keeps only the newest 30 photos', () => {
  const d = dir();
  for (let i = 0; i < 33; i++) saveInboxImages([{ uri: `data:image/png;base64,${jpg.toString('base64')}` }], 'x', d);
  assert.equal(readdirSync(d).length, 30);
});
