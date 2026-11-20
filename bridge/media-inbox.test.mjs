import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, readdirSync, existsSync } from 'node:fs';
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

test('photos of one message are recorded together as an album, a single photo is not, and pruning ignores the album records', () => {
  const d = mkdtempSync(join(tmpdir(), 'inbox-')); const jpg = Buffer.from([0xff, 0xd8, 0xff, 0xd9]); const file = n => ({ uri: `data:image/jpeg;base64,${jpg.toString('base64')}`, name: `${n}.jpg` });
  saveInboxImages([file('a')], 'one', d); assert.equal(existsSync(join(d, '.albums')), false);                    // a single photo: nothing recorded
  const out = saveInboxImages([file('a'), file('b'), file('c')], 'three', d); const paths = [...out.matchAll(/\[Attached photo: (.+?)\]/g)].map(m => m[1]);
  const records = readdirSync(join(d, '.albums')); assert.equal(records.length, 1); assert.deepEqual(JSON.parse(readFileSync(join(d, '.albums', records[0]), 'utf8')).files, paths.map(p => p.split('/').at(-1)));
  for (let k = 0; k < 40; k++) saveInboxImages([file('x')], 'more', d);                                              // pruning keeps the newest 30 photos and never counts or deletes the .albums folder
  assert.equal(existsSync(join(d, '.albums')), true); assert.equal(readdirSync(d).filter(n => !n.startsWith('.')).length <= 30, true);
});
