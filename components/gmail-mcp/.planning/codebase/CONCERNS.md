# Codebase Concerns

**Analysis Date:** 2026-01-27

## Tech Debt

**Email formatting is duplicated:**
- Issue: RFC 2822 email formatting logic is duplicated between `sendMessage()` and `createDraft()`
- Files: `src/tools.ts` lines 226-248 and 358-380
- Impact: Maintenance burden when fixing email format issues, risk of inconsistency between send and draft operations
- Fix approach: Extract RFC 2822 formatting into a shared utility function `formatRfc2822Message()` in `src/tools.ts` and reuse in both functions

**Zod import unused:**
- Issue: `src/index.ts` imports `z` from "zod" on line 10 but never uses it for input validation
- Files: `src/index.ts` line 10
- Impact: Dependency overhead with no functional benefit, misleading code suggesting validation exists when it doesn't
- Fix approach: Remove zod dependency if no validation is intended, or implement input schema validation for all tool parameters using zod

## Security Considerations

**No input validation on Gmail API parameters:**
- Risk: Tool parameters passed directly to Gmail API without validation. Malformed email addresses, excessively long strings, or special characters could cause unexpected behavior
- Files: `src/tools.ts` (sendMessage, createDraft, modifyMessage, listMessages, searchMessages)
- Current mitigation: None - relies on Gmail API error handling
- Recommendations:
  - Implement zod schemas for all tool inputs in `src/index.ts`
  - Validate email addresses in `sendMessage()` and `createDraft()` before sending to API
  - Validate messageId format and label IDs before API calls
  - Add length constraints on subject and body fields

**Credential file stored in plaintext:**
- Risk: OAuth tokens (access and refresh) saved in `credentials.json` as plaintext JSON, readable by any process with filesystem access
- Files: `src/oauth.ts` lines 103-112 (saveCredentials function)
- Current mitigation: File permissions set by system (umask)
- Recommendations:
  - Add file permission check after saving credentials: ensure 0600 (owner read-write only)
  - Consider encryption at rest using Node.js crypto module before persisting
  - Document security implications in README

**Hard-coded redirect URI in fallback:**
- Risk: If OAuth keys file omits redirect_uris, hardcoded `http://localhost:3000/oauth2callback` is used, which may not match registered URI in Google Cloud
- Files: `src/oauth.ts` line 80
- Current mitigation: Assumes standard localhost setup
- Recommendations:
  - Make redirect URI configurable via environment variable `GMAIL_OAUTH_REDIRECT_URI`
  - Validate that configured redirect URI matches Google Cloud registration
  - Warn if localhost URI doesn't match registered production URI

**Minimal error details in base64 decoding:**
- Risk: `decodeBase64Url()` in `src/tools.ts` line 11 will throw if data is invalid, but no validation or sanitization
- Files: `src/tools.ts` lines 9-12
- Current mitigation: Gmail API should validate before returning
- Recommendations:
  - Add try-catch in `extractBody()` to handle invalid base64 gracefully
  - Log decode errors for debugging
  - Return empty string instead of throwing on decode failure

## Performance Bottlenecks

**Sequential message fetching in listMessages:**
- Problem: `listMessages()` fetches list of messages, then makes individual API call for each message to get headers
- Files: `src/tools.ts` lines 73-107 (specifically lines 84-90)
- Cause: Default list response doesn't include headers; code makes N+1 API calls (1 list + N detail calls)
- Improvement path:
  - Use `metadataHeaders` parameter on list call instead of separate get calls
  - If full headers needed, consider batching requests or lazy-loading headers on demand
  - Add `format: "metadata"` with `metadataHeaders` to list request to get headers in single batch
  - Current implementation already does this for list, but could optimize by avoiding extra detail calls for just headers

**No pagination caching or prefetching:**
- Problem: nextPageToken returned but no mechanism to prefetch next page or cache previous results
- Files: `src/tools.ts` lines 104-107
- Cause: Stateless design requires caller to manage pagination
- Improvement path: Document pagination requirement in comments, consider adding cached session support if high-frequency pagination occurs

## Fragile Areas

**Message payload parsing with deeply nested parts:**
- Files: `src/tools.ts` lines 21-36 (processPayload), 152-166 (findAttachments)
- Why fragile: Recursive traversal of email parts assumes consistent structure. Edge cases like circular references (unlikely but possible) or deeply nested MIME structures could cause issues
- Safe modification: Add recursion depth limit (e.g., max 10 levels) to prevent stack overflow on malformed MIME messages
- Test coverage: No tests for complex MIME structures, deeply nested messages, or edge cases like missing mimeType fields

**Non-null assertions throughout:**
- Files: `src/tools.ts` lines 48, 95, 173-174, 259-260, 288-289, 309, 339, 393
- Why fragile: Uses `!` operator extensively (e.g., `msg.id!`, `detail.data.snippet!`). If Gmail API changes response structure or returns undefined, will crash
- Safe modification: Replace with proper null checks and fallbacks
- Test coverage: No unit tests for API response validation

**Hardcoded port 3000 in auth server:**
- Files: `src/auth.ts` line 7
- Why fragile: Port collision will prevent authentication; no fallback to find available port
- Safe modification: Add environment variable `GMAIL_AUTH_PORT` with fallback to 3000, or implement port scanning to find available port
- Test coverage: No tests for port conflict scenario

**No timeout on Gmail API calls:**
- Files: `src/tools.ts` (all API calls via getGmailClient())
- Why fragile: Long-running requests (e.g., large message retrieval) have no timeout; could hang indefinitely
- Safe modification: Add timeout configuration (e.g., 30-60 seconds) to Gmail API client
- Test coverage: No tests for slow/hung requests

## Test Coverage Gaps

**No unit tests exist:**
- What's not tested: All core functionality (oauth flow, email parsing, API calls, error handling)
- Files: `src/` directory (all files lack corresponding .test.ts)
- Risk: Regression bugs when changing oauth.ts or tools.ts, no confidence in refactoring
- Priority: High - critical for email and auth operations

**No integration tests:**
- What's not tested: End-to-end flows like "send email then read it back", "create label then assign it", "handle token refresh mid-operation"
- Files: All coordination between `src/oauth.ts` and `src/tools.ts`
- Risk: Token refresh timing issues, API call failures, message format issues won't be caught
- Priority: High - catches real-world scenarios

**No error scenario testing:**
- What's not tested: Authentication failures, malformed email responses, API rate limits, network errors, file permission errors
- Files: `src/oauth.ts` (error paths), `src/tools.ts` (API error handling), `src/index.ts` (error responses)
- Risk: Error messages may be unclear or unhelpful; recovery paths untested
- Priority: Medium - improves user experience and debugging

**No MIME parsing edge case testing:**
- What's not tested: Messages with missing mimeType, no parts, deeply nested parts, attachment-only messages
- Files: `src/tools.ts` (extractBody, findAttachments functions)
- Risk: Crashes or data loss when reading complex email formats
- Priority: Medium - affects reliability with diverse email types

## Scaling Limits

**Single-threaded node process:**
- Current capacity: Limited by single V8 thread; CPU-bound work blocks all operations
- Limit: High volume of concurrent API calls or large message processing could saturate thread
- Scaling path: Worker threads or clustering not needed unless >100 concurrent tool invocations; consider load testing at 50 concurrent requests

**Credentials file I/O on every API call:**
- Current capacity: Assumes local filesystem; reading credentials from disk on each request
- Limit: Frequent reads add latency (~1-5ms per read); in-memory caching would improve performance
- Scaling path: Add in-memory credential cache with 5-minute TTL to reduce filesystem I/O
- Implementation: Store last-loaded credentials in module variable, only refresh on expiry

**No request rate limiting:**
- Current capacity: Code makes unlimited concurrent requests to Gmail API
- Limit: Google Cloud quotas (100 QPS default) will be hit quickly with many concurrent tool calls
- Scaling path: Implement request queue with max concurrency (e.g., 5 simultaneous API calls), add backoff on 429 errors

## Dependencies at Risk

**googleapis package (v144.0.0):**
- Risk: Major dependency on Google's auto-generated API client; prone to breaking changes
- Impact: API changes or removals (rare but possible) require client updates
- Migration plan: Pin to stable version, monitor googleapis changelog quarterly, test API responses in CI

**@modelcontextprotocol/sdk (v1.0.0):**
- Risk: Early-stage MCP SDK; API may change between versions
- Impact: Updates could require refactoring of server.setRequestHandler() calls
- Migration plan: Lock version in package-lock.json, test upgrades in staging before deploying

## Missing Critical Features

**No offline support:**
- Problem: Cannot function without internet; all reads/writes require live API
- Blocks: Using Gmail MCP on disconnected systems, caching frequently-accessed emails

**No attachment download support:**
- Problem: `readMessage()` returns attachment metadata but not content
- Blocks: Claude from accessing email attachments (PDFs, images, etc.)
- Workaround: User must download manually from Gmail

**No thread/conversation support:**
- Problem: Tools don't group messages by thread despite `threadId` being available
- Blocks: Viewing complete conversations or replying to specific message in thread
- Workaround: Must reconstruct thread manually by searching and reading individual messages

**No label creation in authenticated flow:**
- Problem: Label operations require label IDs; no way to get user-created label IDs other than `listLabels()`
- Blocks: Creating new labels during authenticated flow
- Workaround: Must run `listLabels()` first, then use returned IDs

**No draft deletion:**
- Problem: Can create and send drafts but cannot delete unwanted drafts
- Blocks: Cleanup of draft workspace

---

*Concerns audit: 2026-01-27*
