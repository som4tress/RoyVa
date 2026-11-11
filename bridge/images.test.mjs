import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { generatedImages, sendPhotos } from './images.mjs';

const dir = mkdtempSync(join(tmpdir(), 'imgs-'));
const good = join(dir, 'a.png'); writeFileSync(good, Buffer.alloc(2000));
const call = (name, status, payload) => ({ type: 'assistant', content: [{ type: 'tool', name, state: { status, content: [{ type: 'text', text: JSON.stringify(payload) }] } }] });

test('collects the picture from a completed generate_image call', () => {
  assert.deepEqual(generatedImages([call('image-gen_generate_image', 'completed', { ok: true, image_path: good })], dir), [good]);
});
test('ignores failures, other tools, errors, missing files and duplicates', () => {
  const rows = [call('image-gen_generate_image', 'completed', { ok: false, error: 'busy' }), call('ha-speakers_speak', 'completed', { ok: true, image_path: good }),
    call('image-gen_generate_image', 'error', { ok: true, image_path: good }), call('image-gen_generate_image', 'completed', { ok: true, image_path: join(dir, 'gone.png') }),
    call('image-gen_generate_image', 'completed', { ok: true, image_path: good }), call('image-gen_generate_image', 'completed', { ok: true, image_path: good })];
  assert.deepEqual(generatedImages(rows, dir), [good]);
});
test('never uploads a file outside the images folder (even if a tool result names one)', () => {
  const other = mkdtempSync(join(tmpdir(), 'other-')); const evil = join(other, 'secret.png'); writeFileSync(evil, Buffer.alloc(2000));
  assert.deepEqual(generatedImages([call('image-gen_generate_image', 'completed', { ok: true, image_path: evil })], dir), []);
  assert.deepEqual(generatedImages([call('image-gen_generate_image', 'completed', { ok: true, image_path: join(dir, '..', 'x.png') })], dir), []);
});
test('sendPhotos posts each file to sendPhoto with the reply target, and throws when Telegram refuses', async () => {
  const seen = [];
  await sendPhotos('TOKEN', 42, [good], 7, async (url, init) => { seen.push([url, init.body.get('chat_id'), init.body.get('reply_parameters'), init.body.get('photo').type]); return { json: async () => ({ ok: true }) }; });
  assert.deepEqual(seen, [['https://api.telegram.org/botTOKEN/sendPhoto', '42', JSON.stringify({ message_id: 7, allow_sending_without_reply: true }), 'image/png']]);
  await assert.rejects(sendPhotos('T', 1, [good], 0, async () => ({ json: async () => ({ ok: false, error_code: 400 }) })), /sendPhoto: 400/);
});
