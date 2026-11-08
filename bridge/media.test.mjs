import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { withVideoFrames } from './media.mjs';

test('images pass through untouched', async () => {
  const files = [{ uri: 'data:image/jpeg;base64,AAAA', name: 'a.jpg' }];
  const out = await withVideoFrames(files, 'what is this');
  assert.deepEqual(out.files, files); assert.equal(out.text, 'what is this');
});

test('a video becomes ordered image frames plus a note that audio is not included', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'vid-')); const f = join(dir, 'c.mp4');
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc=d=3:s=160x120:r=10', f]);
  const out = await withVideoFrames([{ uri: `data:video/mp4;base64,${readFileSync(f).toString('base64')}`, name: 'c.mp4' }], 'what happens');
  assert.ok(out.files.length >= 2 && out.files.every(x => x.uri.startsWith('data:image/jpeg')));
  assert.match(out.text, /Video .*frames in chronological order/); assert.match(out.text, /audio is not included/i);
});
