# Architecture

**Analysis Date:** 2026-01-27

## Pattern Overview

**Overall:** Model Context Protocol (MCP) Server with OAuth2-authenticated external service integration

**Key Characteristics:**
- Stdio-based MCP server implementing the Model Context Protocol specification
- Layered architecture separating OAuth/authentication concerns from Gmail API interactions
- Tool-based RPC pattern where each Gmail function maps to a callable MCP tool
- Persistent credential management with automatic token refresh
- Stateless tool handlers receiving arguments and returning JSON results

## Layers

**MCP Server Layer:**
- Purpose: Handles Model Context Protocol communication and tool routing
- Location: `src/index.ts`
- Contains: Server initialization, tool definitions, request dispatching
- Depends on: MCP SDK, tool implementations
- Used by: MCP client (external)

**Tool Implementation Layer:**
- Purpose: Implements Gmail-specific operations and message parsing
- Location: `src/tools.ts`
- Contains: Message listing, reading, searching, sending, drafting, label management
- Depends on: Gmail API client, OAuth authentication
- Used by: MCP server layer

**OAuth/Authentication Layer:**
- Purpose: Manages OAuth2 flow, credential persistence, and token lifecycle
- Location: `src/oauth.ts`, `src/auth.ts`
- Contains: OAuth client initialization, credential loading/saving, token refresh logic
- Depends on: Google APIs library, Node.js fs/os modules
- Used by: Tool implementation layer

## Data Flow

**Authentication Flow:**

1. User runs `gmail-mcp auth` command
2. `auth.ts` initiates OAuth2 flow, generates auth URL
3. User visits auth URL in browser, approves access
4. Google redirects to localhost:3000/oauth2callback with authorization code
5. `auth.ts` exchanges code for access/refresh tokens
6. Credentials saved to disk at `~/.gmail-mcp/credentials.json`

**Request/Response Flow:**

1. MCP client sends CallToolRequest via stdio
2. `index.ts` routes request to appropriate tool handler based on tool name
3. Tool handler (e.g., `listMessages`) calls `getGmailClient()`
4. `oauth.ts` loads credentials from disk, refreshes if expired (auto-refresh)
5. Gmail API call executes with authenticated client
6. Results parsed/transformed by tool handler
7. JSON response returned to MCP client

**Token Refresh Flow:**

1. Before each Gmail API call, `getAuthenticatedClient()` is invoked
2. Credentials loaded fresh from disk
3. Expiry checked: if expired or expiring within 5 minutes, refresh triggered
4. `refreshAccessToken()` uses refresh token to obtain new access token
5. Updated credentials saved to disk immediately
6. Client configured with valid tokens

**State Management:**
- Credentials stored as JSON file on disk (not in memory)
- Each request reads fresh credentials from disk
- Token refresh happens transparently before API calls
- No in-process session state

## Key Abstractions

**Tool Definition:**
- Purpose: Declarative specification of MCP tool (name, description, input schema)
- Examples: `list_messages`, `read_message`, `send_message` in `src/index.ts`
- Pattern: Plain JavaScript object with name, description, and Zod-compatible JSON schema

**Credential Management:**
- Purpose: Abstraction over credential file I/O and refresh logic
- Examples: `loadCredentials()`, `saveCredentials()`, `refreshAccessToken()` in `src/oauth.ts`
- Pattern: Functions that always read from disk, handle refresh automatically

**Message Parsing:**
- Purpose: Extract structured data from Gmail API responses
- Examples: `extractBody()`, `getHeader()`, `findAttachments()` in `src/tools.ts`
- Pattern: Recursive payload traversal for MIME parts, base64url decoding

**RFC 2822 Message Construction:**
- Purpose: Build raw email format for sending/drafting
- Examples: Used in `sendMessage()` and `createDraft()` in `src/tools.ts`
- Pattern: Build header lines, encode body as base64url, set threadId for replies

## Entry Points

**MCP Server:**
- Location: `src/index.ts` (line 309-318)
- Triggers: `npm start` or direct invocation
- Responsibilities: Create StdioServerTransport, connect server, handle tool requests

**Authentication Script:**
- Location: `src/auth.ts` (line 119-122)
- Triggers: `npm run auth` or `gmail-mcp auth`
- Responsibilities: OAuth2 flow, local callback server, credential persistence

## Error Handling

**Strategy:** Try-catch wrapping at tool call level with error message returned to client

**Patterns:**
- Missing credentials: Throws "No credentials found" with instruction to run auth
- Expired refresh token: Throws error with re-authentication instruction
- Missing OAuth keys file: Throws with file path guidance
- API errors: Caught in CallToolRequestSchema handler, returned as MCP error response
- Missing required params: Schema validation prevents invalid calls

## Cross-Cutting Concerns

**Logging:**
- Uses `console.error()` for authentication flow status
- Uses `console.log()` for server startup/shutdown
- No structured logging framework

**Validation:**
- Input validation via MCP schema definitions in tool objects
- TypeScript type checking for function parameters
- OAuth keys/credentials validated at load time

**Authentication:**
- Google OAuth2 with PKCE/authorization code flow
- Refresh token stored persistently
- Automatic token refresh on expiry (5-minute buffer)
- Multi-account support via GMAIL_CREDENTIALS_PATH env var
