# External Integrations

**Analysis Date:** 2026-01-27

## APIs & External Services

**Google Gmail API:**
- Service: Gmail REST API (v1)
- What it's used for: Email listing, reading, searching, sending, modifying labels, draft management
- SDK/Client: `googleapis` v144.0.0 (imported as `gmail_v1` type in `src/tools.ts`)
- Auth: OAuth 2.0 with refresh token flow

**Google OAuth 2.0:**
- Service: Google Cloud authentication
- What it's used for: User authorization and token management
- SDK/Client: `googleapis` package OAuth2 module
- Scopes implemented: `src/oauth.ts` line 6-12
  - `https://www.googleapis.com/auth/gmail.readonly` - Read emails
  - `https://www.googleapis.com/auth/gmail.send` - Send emails
  - `https://www.googleapis.com/auth/gmail.compose` - Compose emails
  - `https://www.googleapis.com/auth/gmail.modify` - Modify labels and messages
  - `https://www.googleapis.com/auth/gmail.labels` - Manage labels
- Flow: OAuth2 code exchange via local HTTP server (`src/auth.ts` port 3000)

## Authentication & Identity

**Auth Provider:**
- Service: Google OAuth 2.0
- Implementation: Custom OAuth2 client creation in `src/oauth.ts`
  - OAuth2Client instantiation: Line 117-124
  - Credentials file-based storage: Lines 103-112
  - Automatic token refresh with 5-minute expiry buffer: Lines 130-189

**Credential Storage:**
- Location: File-based (not cloud storage)
- Credentials file path: `~/.gmail-mcp/credentials.json` (configurable via `GMAIL_CREDENTIALS_PATH`)
- OAuth keys file: `~/.gmail-mcp/gcp-oauth.keys.json` (configurable via `GMAIL_OAUTH_KEYS_PATH`)
- Format: JSON files with access/refresh tokens and expiry dates

**Token Management:**
- Access tokens: Auto-refreshed when expired or expiring within 5 minutes
- Refresh tokens: Preserved across token refreshes; stored on disk immediately after refresh
- Implementation: `getAuthenticatedClient()` in `src/oauth.ts` (lines 157-199)

## Data Storage

**Local File System:**
- Credentials stored at: `~/.gmail-mcp/credentials.json`
- OAuth keys stored at: `~/.gmail-mcp/gcp-oauth.keys.json`
- Both paths support `~` expansion and environment variable overrides

**Gmail Cloud Storage:**
- Messages stored in Gmail account
- No local database or caching layer
- Real-time API calls for each operation

## Webhooks & Callbacks

**Incoming:**
- OAuth2 callback endpoint: `http://localhost:3000/oauth2callback` (local HTTP server in `src/auth.ts`)
- Receives authorization code after user grants permissions in Google login flow
- No persistent webhook subscriptions to Gmail

**Outgoing:**
- None. MCP server receives tool calls from client and returns synchronous responses.

## Environment Configuration

**Required env vars:**
- `GMAIL_CREDENTIALS_PATH` - Path to credentials.json (default: `~/.gmail-mcp/credentials.json`)
- `GMAIL_OAUTH_KEYS_PATH` - Path to gcp-oauth.keys.json (default: `~/.gmail-mcp/gcp-oauth.keys.json`)

**Secrets location:**
- Credentials stored locally in `~/.gmail-mcp/credentials.json` - contains access_token, refresh_token, expiry_date
- OAuth keys in `~/.gmail-mcp/gcp-oauth.keys.json` - contains client_id, client_secret, redirect_uris
- No environment variables store secrets directly; paths to secret files are environment-configurable

**Setup Requirements:**
1. Create Google Cloud Project and OAuth credentials (Desktop app type)
2. Download credentials JSON from Google Cloud Console
3. Save to `~/.gmail-mcp/gcp-oauth.keys.json` (or path specified by `GMAIL_OAUTH_KEYS_PATH`)
4. Run `npm run auth` or `npx gmail-mcp-server auth` to authenticate
5. Credentials are saved to `~/.gmail-mcp/credentials.json` after successful OAuth flow

## MCP (Model Context Protocol)

**Server Implementation:**
- Framework: `@modelcontextprotocol/sdk` v1.0.0
- Transport: Stdio (standard input/output)
- Implementation: `src/index.ts`
- Tools exposed: 8 total
  - `list_messages` - List emails with pagination
  - `read_message` - Get full message content
  - `search_messages` - Search with Gmail query syntax
  - `send_message` - Send new email
  - `modify_message` - Add/remove labels, mark read/unread
  - `list_labels` - List all labels
  - `create_label` - Create new label
  - `create_draft` - Create draft email
  - `send_draft` - Send existing draft

**Tool Invocation Flow:**
1. Client sends `CallToolRequest` via MCP protocol
2. `src/index.ts` CallToolRequestSchema handler routes to appropriate tool function
3. Tool function in `src/tools.ts` calls Gmail API via authenticated client
4. Result serialized to JSON and returned to client

## API Rate Limiting

**Gmail API Quotas:**
- Not explicitly handled in code
- Default Google API quotas apply
- Potential concerns: Batch operations in `listMessages()` make individual API calls per message (lines 84-101 in `src/tools.ts`)

## Error Handling

**OAuth Errors:**
- Token refresh failures: Caught in `getAuthenticatedClient()` (lines 182-188), user directed to re-authenticate
- Missing credentials: Error thrown if `credentials.json` not found
- Missing refresh token: Error thrown, user directed to re-authenticate

**API Errors:**
- Gmail API errors: Caught in tool handlers, serialized to error response
- All errors returned via MCP error response with `isError: true` flag

---

*Integration audit: 2026-01-27*
