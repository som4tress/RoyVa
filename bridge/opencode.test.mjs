import assert from 'node:assert/strict';
import test from 'node:test';
import { runLimitMs, runText, RUN_LIMIT_MS, MEDIA_RUN_LIMIT_MS } from './opencode.mjs';

const tool = name => ({ content: [{ type: 'tool', name, state: { status: 'running' } }] });

test('a normal request keeps the 15 minute limit', () => {
  assert.equal(runLimitMs([]), RUN_LIMIT_MS);
  assert.equal(runLimitMs([tool('home-assistant_GetLiveContext'), { content: [{ type: 'text', text: 'hi' }] }]), RUN_LIMIT_MS);
});

test('a picture or video tool extends the limit, and it never shrinks again', () => {
  for (const name of ['img-video_generate_video', 'img-video_generate_image_set', 'image-gen_generate_image', 'image-gen_edit_image']) assert.equal(runLimitMs([tool(name)]), MEDIA_RUN_LIMIT_MS, name);
  assert.equal(runLimitMs([{ content: [{ type: 'text', text: 'done' }] }], MEDIA_RUN_LIMIT_MS), MEDIA_RUN_LIMIT_MS);
  assert.ok(MEDIA_RUN_LIMIT_MS > 30 * 60 * 1000);                       // longer than the tool's own 30 minute synchronous timeout
});

test('a run that finishes quickly still returns the answer', async () => {
  let calls = 0;
  const api = async (path) => {
    if (path.endsWith('/message')) return calls++ ? [{ id: 'u', type: 'user', time: { created: 5 }, content: [] }, { id: 'a', type: 'assistant', time: { created: 6 }, content: [{ type: 'text', text: 'answer' }] }] : [];
    if (path.endsWith('/permission')) return [];
    if (path.endsWith('/prompt')) return {};
    return { time: { idle: 10, busy: 1 } };
  };
  assert.equal(await runText('s1', 'q', { api }), 'answer');
});
