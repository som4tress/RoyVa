import {test, mock} from 'node:test';
import assert from 'node:assert/strict';
let data, requests;
const gmail = {users: {messages: {
  list: async params => {requests.push(params); return {data};},
  get: async ({id}) => ({data: {snippet: id, payload: {headers: [{name: 'From', value: 'fixture@example.test'}]}, labelIds: ['INBOX']}}),
}}};
mock.module(new URL('../dist/oauth.js', import.meta.url).href, {namedExports: {getGmailClient: async () => gmail}});
const {listMessages, searchMessages} = await import('../dist/tools.js');
function fixture(count, extra = {}) {
  data = {messages: Array.from({length: count}, (_, i) => ({id: `message-${i}`, threadId: `thread-${i}`})), ...extra};
  requests = [];
}
test('list returns exact page count independently of approximate total', async () => {
  fixture(38, {resultSizeEstimate: 42});
  const result = await listMessages({maxResults: 100});
  assert.equal(result.returned_count, 38);
  assert.equal(result.messages.length, 38);
  assert.equal(result.total_estimate, 42);
  assert.equal(result.has_more, false);
});
test('search exposes pagination without fetching subsequent pages automatically', async () => {
  fixture(100, {nextPageToken: 'next', resultSizeEstimate: 420});
  const result = await searchMessages({query: 'from:paypal', maxResults: 100});
  assert.equal(result.returned_count, 100);
  assert.equal(result.has_more, true);
  assert.equal(result.nextPageToken, 'next');
  assert.equal(result.total_estimate, 420);
  assert.equal(requests.length, 1);
});
test('explicit next-page request reports that page count, not a cumulative total', async () => {
  fixture(14);
  const result = await searchMessages({query: 'from:openai', pageToken: 'previous'});
  assert.equal(requests[0].pageToken, 'previous');
  assert.equal(result.returned_count, 14);
  assert.equal(result.has_more, false);
  assert.equal(result.total_estimate, null);
});
test('zero results retain count metadata and broader-search suggestions', async () => {
  fixture(0, {resultSizeEstimate: 0});
  const result = await searchMessages({query: 'from:usps after:2026/01/01'});
  assert.equal(result.returned_count, 0);
  assert.equal(result.has_more, false);
  assert.equal(result.total_estimate, 0);
  assert(result.suggestions);
});
test('an omitted message array still produces explicit zero and unknown estimate', async () => {
  data = {}; requests = [];
  const result = await listMessages({});
  assert.equal(result.returned_count, 0);
  assert.deepEqual(result.messages, []);
  assert.equal(result.has_more, false);
  assert.equal(result.total_estimate, null);
});
