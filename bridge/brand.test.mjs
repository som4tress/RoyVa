import test from 'node:test';
import assert from 'node:assert/strict';
import {brandFrom} from './brand.mjs';

test('defaults: product Lares, assistant Roy, /roy command', () => {
  const b = brandFrom({});
  assert.deepEqual([b.product, b.assistant, b.command], ['Lares', 'Roy', 'roy']);
});
test('config values are used and the command is sanitized', () => {
  const b = brandFrom({LARES_PRODUCT: 'Acme', LARES_ASSISTANT_NAME: 'Jarvis', LARES_COMMAND: '/Jarvis!'});
  assert.deepEqual([b.product, b.assistant, b.command], ['Acme', 'Jarvis', 'jarvis']);
});
test('back pattern accepts the command, the legacy /royva alias and @bot, and nothing else', () => {
  const {backPattern} = brandFrom({LARES_COMMAND: 'jarvis'});
  for (const ok of ['/jarvis', ' /royva ', '/JARVIS@my_bot']) assert.match(ok, backPattern);
  for (const no of ['/jarvis now', 'jarvis', '/roy']) assert.doesNotMatch(no, backPattern);
});
