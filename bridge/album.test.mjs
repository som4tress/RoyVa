import assert from 'node:assert/strict';
import test from 'node:test';
import {createAlbumCollector, mergeAlbum, telegramAlbumMedia, MAX_ALBUM} from './media.mjs';

const photo = (id, extra = {}) => ({message_id: id, chat: {id: 7, type: 'private'}, from: {id: 7}, media_group_id: 'g1', photo: [{file_id: `f${id}`}], ...extra});
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

test('photos of one album become ONE message: ordered, the caption kept, every photo listed', () => {
  const merged = mergeAlbum([photo(12), photo(10, {caption: 'Make the husband and wife walk through Paris'}), photo(11)]);
  assert.deepEqual(merged._album.map(m => m.message_id), [10, 11, 12]);
  assert.equal(merged.caption, 'Make the husband and wife walk through Paris'); assert.equal(merged.message_id, 10);
  assert.equal(mergeAlbum([photo(2), photo(1)]).caption, '');                                   // no caption anywhere: empty, never undefined
  assert.equal(mergeAlbum(Array.from({length: 14}, (_, i) => photo(i + 1)))._album.length, MAX_ALBUM);
});

test('the collector waits for the quiet period, then hands over one album per group', async () => {
  const got = []; const c = createAlbumCollector(album => got.push(album), 40);
  c.add(photo(1, {caption: 'hi'})); await wait(15); c.add(photo(2)); await wait(15); c.add(photo(3));    // each photo restarts the wait
  assert.equal(got.length, 0); assert.equal(c.pending, 1);
  await wait(90); assert.equal(got.length, 1); assert.equal(got[0]._album.length, 3); assert.equal(c.pending, 0);
});

test('two albums at the same time stay separate, in different chats too', async () => {
  const got = []; const c = createAlbumCollector(album => got.push(album), 30);
  c.add(photo(1)); c.add({...photo(2), media_group_id: 'g2'}); c.add({...photo(3), chat: {id: 8}}); c.add(photo(4));
  await wait(80); assert.equal(got.length, 3);
  assert.deepEqual(got.map(a => a._album.map(m => m.message_id)).sort(), [[1, 4], [2], [3]]);
});

test('a message that is not part of an album is downloaded exactly as before', async () => {
  const calls = []; const tg = async (method, args) => { calls.push([method, args.file_id]); return {file_path: 'x'}; };
  const single = {photo: [{file_id: 'a', file_size: 5}]};
  // no _album: telegramAlbumMedia must go straight to telegramMedia (which downloads); here the download fails on the fake path, which proves the same code path ran
  await assert.rejects(() => telegramAlbumMedia(single, tg, 'T'));
  assert.deepEqual(calls, [['getFile', 'a']]);
});
