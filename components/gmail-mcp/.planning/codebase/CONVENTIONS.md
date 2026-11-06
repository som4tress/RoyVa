# Coding Conventions

**Analysis Date:** 2026-01-27

## Naming Patterns

**Files:**
- Lowercase with `.ts` extension
- Descriptive names matching primary responsibility: `oauth.ts`, `tools.ts`, `auth.ts`, `index.ts`
- Entry point is `index.ts`
- Utility modules are grouped by function (oauth, tools)

**Functions:**
- camelCase for function names
- Descriptive, action-oriented names: `listMessages`, `readMessage`, `searchMessages`, `sendMessage`, `modifyMessage`, `listLabels`, `createLabel`, `createDraft`, `sendDraft`, `getAuthenticatedClient`, `getGmailClient`, `loadOAuthKeys`, `saveCredentials`, `decodeBase64Url`, `extractBody`, `getHeader`
- Private/internal functions: `resolvePath`, `getCredentialsPath`, `getOAuthKeysPath`, `loadCredentials`, `refreshAccessToken`, `createOAuth2Client`, `processPayload`, `findAttachments`

**Variables:**
- camelCase for variable names
- Descriptive names that clearly indicate type/purpose: `oauth2Client`, `messageParts`, `encodedMessage`, `response`, `credentials`, `keysPath`, `credPath`, `headers`, `labelIds`, `attachments`, `threadId`
- Constants in UPPERCASE: `SCOPES`, `PORT`, `GMAIL_CREDENTIALS_PATH`, `GMAIL_OAUTH_KEYS_PATH`

**Types & Interfaces:**
- PascalCase for type names: `Credentials`, `OAuthKeys`, `Gmail` (imported type alias)
- Inline object type definitions using `type` keyword with object literals
- Generic parameters using standard conventions: `T`, `Schema$MessagePart`

## Code Style

**Formatting:**
- TypeScript with no explicit formatter configured (ESLint/Prettier not detected)
- Indentation: 2 spaces (inferred from source)
- Line length: No strict limit observed
- Trailing semicolons: Present in all statements
- Quotes: Double quotes for strings consistently throughout

**Linting:**
- No ESLint config detected
- No Prettier config detected
- TypeScript strict mode enabled in `tsconfig.json` with settings:
  - `strict: true`
  - `esModuleInterop: true`
  - `skipLibCheck: true`
  - `forceConsistentCasingInFileNames: true`

## Import Organization

**Order:**
1. Node built-in modules first (`import * as fs from "fs"`, `import * as path from "path"`)
2. Third-party packages next (`import { google } from "googleapis"`, `import { z } from "zod"`)
3. Local modules last (`import { ... } from "./tools.js"`, `import { ... } from "./oauth.js"`)

**Path Aliases:**
- No path aliases configured
- Direct relative imports with `.js` extension (ESM modules): `from "./tools.js"`, `from "./oauth.js"`

**Example from `src/index.ts`:**
```typescript
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ToolSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import {
  listMessages,
  readMessage,
  // ... more imports
} from "./tools.js";
```

## Error Handling

**Patterns:**
- `try-catch` blocks with explicit error handling
- Error messages include context: `throw new Error("OAuth keys file not found: " + path)`
- Type guards for error checking: `error instanceof Error ? error.message : String(error)`
- Synchronous error throwing for validation failures
- Asynchronous errors caught with `.catch()` chaining
- Tool execution errors wrapped in response object with `isError: true` flag

**Example from `src/index.ts`:**
```typescript
try {
  let result: unknown;
  switch (name) {
    case "list_messages":
      result = await listMessages(args as Parameters<typeof listMessages>[0]);
      break;
    // ... other cases
  }
  return {
    content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
  };
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  return {
    content: [{ type: "text", text: `Error: ${message}` }],
    isError: true,
  };
}
```

**Example from `src/oauth.ts`:**
```typescript
try {
  validCredentials = await refreshAccessToken(oauth2Client, credentials);
} catch (error) {
  throw new Error(
    `Failed to refresh access token: ${error}. Run 'gmail-mcp auth' to re-authenticate.`
  );
}
```

## Logging

**Framework:** `console` module (no dedicated logging library)

**Patterns:**
- `console.log()` for informational/success messages
- `console.error()` for error messages and warnings
- `console.warn()` for non-critical warnings
- Context-rich messages with formatted output
- Server startup/shutdown logged to stderr

**Example from `src/auth.ts`:**
```typescript
console.log("\n=== Gmail MCP Authentication ===\n");
console.log("Opening browser for authentication...");
console.warn("\nWarning: No refresh token received. You may need to revoke access and re-authenticate.");
console.error("Error during authentication:", err);
```

**Example from `src/index.ts`:**
```typescript
console.error("Gmail MCP server running on stdio");
```

## Comments

**When to Comment:**
- JSDoc-style comments for all exported functions and public APIs
- Inline comments for non-obvious logic (RFC 2822 formatting, base64 encoding)
- Explanatory comments for important algorithm steps (token refresh logic)
- Comments highlight key design decisions (e.g., "always reads from disk and refreshes if needed")

**JSDoc/TSDoc:**
- Multi-line JSDoc blocks for all exported functions
- Include purpose description
- No parameter documentation observed
- Focus on high-level behavior explanation

**Example from `src/oauth.ts`:**
```typescript
/**
 * Resolves ~ to home directory and normalizes path
 */
function resolvePath(p: string): string {
  if (p.startsWith("~")) {
    return path.join(os.homedir(), p.slice(1));
  }
  return path.resolve(p);
}

/**
 * Refreshes the access token using the refresh token
 * This is the KEY function that the other MCP got wrong
 */
async function refreshAccessToken(oauth2Client: Auth.OAuth2Client, credentials: Credentials): Promise<Credentials> {
```

## Function Design

**Size:** Functions range from 5 to 50+ lines; utility functions are compact (5-20 lines), while API interaction functions are larger (20-50 lines) due to complex data transformation

**Parameters:**
- Functions accept objects (destructured) for multiple parameters: `{ messageId: string, addLabelIds?: string[], removeLabelIds?: string[] }`
- Type annotations required (TypeScript strict mode)
- Optional parameters marked with `?`

**Return Values:**
- Explicitly typed return values: `Promise<{ id: string; threadId: string }>`, `Credentials`, `OAuthKeys`
- Objects with descriptive property names
- Consistent naming of returned objects (e.g., always returns `{ id, threadId }` patterns)

**Example from `src/tools.ts`:**
```typescript
export async function listMessages(params: {
  maxResults?: number;
  labelIds?: string[];
  q?: string;
  pageToken?: string;
}): Promise<{
  messages: Array<{
    id: string;
    threadId: string;
    snippet: string;
    from: string;
    subject: string;
    date: string;
    labelIds: string[];
  }>;
  nextPageToken?: string;
}> {
  // ... implementation
}
```

## Module Design

**Exports:**
- Named exports for functions: `export async function listMessages(...)`, `export function getAuthenticatedClient()`
- No default exports
- Tool functions exported individually from `src/tools.ts`
- Auth utilities exported from `src/oauth.ts`

**Barrel Files:**
- Not used; all exports are direct from implementation files
- Index file (`src/index.ts`) aggregates tool definitions and handles server logic

**Example from `src/oauth.ts`:**
```typescript
export async function getAuthenticatedClient(): Promise<Auth.OAuth2Client> {
export async function getGmailClient() {
export { SCOPES, createOAuth2Client, saveCredentials, loadCredentials };
```

## Type Safety

**TypeScript Features:**
- Strict mode enabled: All variables and returns must be typed
- Non-null assertion operator (`!`) used when APIs guarantee non-null values: `msg.id!`, `response.data.id!`
- Type casting with `as` for parameter type narrowing: `args as Parameters<typeof listMessages>[0]`
- Type aliases for complex return types and imported types: `type Gmail = gmail_v1.Gmail`
- Inline object type definitions for API parameters and responses

**Example from `src/index.ts`:**
```typescript
const { name, arguments: args } = request.params;
result = await listMessages(args as Parameters<typeof listMessages>[0]);
```

---

*Convention analysis: 2026-01-27*
