# Testing Patterns

**Analysis Date:** 2026-01-27

## Test Framework

**Status:** No testing framework configured or detected

**Package.json Scripts:**
```json
{
  "build": "tsc",
  "dev": "tsc --watch",
  "start": "node dist/index.js",
  "auth": "node dist/auth.js"
}
```

**Observations:**
- No test script in `package.json`
- No testing dependencies: Jest, Vitest, Mocha, or similar not installed
- No test configuration files detected: `jest.config.js`, `vitest.config.ts`, `mocha.opts`
- No assertion libraries detected

## Test File Organization

**Status:** No test files in project

**Current Practice:**
- Application code only in `src/` directory
- No separate `tests/` or `__tests__/` directories
- No co-located test files (`.test.ts` or `.spec.ts`)
- Development tested manually or through external integration

## Testing Approach

**Current Method:**
- Manual testing through CLI:
  - `npm run build` compiles TypeScript
  - `npm start` runs the server
  - `npm run auth` runs the authentication flow
  - Integration tested against actual Gmail API

**Integration Testing:**
- Auth flow tested by running `node dist/auth.js` which:
  - Opens browser for OAuth2 consent
  - Spins up local HTTP server on port 3000
  - Receives and exchanges authorization code
  - Saves credentials to file system
- Gmail API operations tested by making actual API calls through `googleapis` library

## Code Testability Patterns

**Architecture for Testing:**
- Separation of concerns supports testing:
  - `src/oauth.ts`: OAuth2 client setup and token management (testable in isolation)
  - `src/tools.ts`: Individual API operations (require authenticated client)
  - `src/auth.ts`: Authentication flow (requires HTTP server and browser)
  - `src/index.ts`: Tool server and request routing

**Key Testable Units:**

**`src/oauth.ts` Functions:**
- `resolvePath()`: Pure function, highly testable
- `getCredentialsPath()`: Env variable reading, testable with mocks
- `getOAuthKeysPath()`: Env variable reading, testable with mocks
- `loadOAuthKeys()`: File I/O, requires file fixtures
- `loadCredentials()`: File I/O, requires file fixtures
- `saveCredentials()`: File I/O side-effects
- `createOAuth2Client()`: OAuth2 client initialization
- `refreshAccessToken()`: Token refresh logic with API interaction
- `getAuthenticatedClient()`: Token validation and refresh orchestration

**`src/tools.ts` Functions:**
All export async functions that require Gmail API authentication. Current structure makes testing challenging because:
- All functions require authenticated Gmail client via `getGmailClient()`
- Functions directly call actual Gmail API endpoints
- No dependency injection for mocking the Gmail API
- Complex data transformation logic interspersed with API calls

**`src/index.ts` Request Handler:**
- Tool handler is MCP request/response handler
- Difficult to test without MCP SDK infrastructure
- Try-catch pattern catches and formats all errors

## Test Gaps

**Missing Test Coverage:**

**Authentication Logic (`src/oauth.ts`):**
- Token refresh timing (expiry buffer = 5 minutes)
- Path resolution with `~` home directory expansion
- OAuth key loading from different credential formats (`web` vs `installed`)
- Error cases: missing credentials file, invalid JSON, missing required fields
- File system operations (read/write) and permissions

**Tool Operations (`src/tools.ts`):**
- Message listing with pagination (`nextPageToken`)
- Message search with Gmail query syntax
- Base64 URL decoding and RFC 2822 email formatting
- Attachment extraction and metadata parsing
- Multi-part message parsing for text and HTML bodies
- Label creation and message modification
- Draft creation and sending

**Error Handling:**
- Network errors (API timeouts, connection failures)
- API errors (invalid message IDs, permission denied)
- Malformed responses from Gmail API
- Invalid input validation (missing required parameters)

**Authentication Flow (`src/auth.ts`):**
- OAuth callback handling
- Authorization code exchange
- Port binding errors
- Browser opening (the `open` package optional import)

## Dependency Structure for Testing

**External Dependencies That Would Need Mocking:**
```typescript
// From googleapis library
google.auth.OAuth2
google.gmail()

// From Node built-ins
fs (file system operations)
path (path operations)
http.createServer() (auth callback server)
```

**Environment Dependencies:**
- Env vars: `GMAIL_CREDENTIALS_PATH`, `GMAIL_OAUTH_KEYS_PATH`
- File system paths: `~/.gmail-mcp/credentials.json`, `~/.gmail-mcp/gcp-oauth.keys.json`
- External OAuth provider: Google OAuth2 endpoint
- Gmail API service

## Recommendations for Testing

**Unit Testing Setup:**
1. Install testing framework:
   - Vitest (recommended for ES modules)
   - Jest with ESM configuration

2. Mock external dependencies:
   - `googleapis` OAuth2 client and gmail API
   - Node `fs` and `path` modules
   - HTTP server creation

3. Create test fixtures:
   - Sample credentials JSON
   - Sample OAuth keys JSON
   - Sample Gmail API responses

**Test Structure Pattern to Follow:**

For `src/oauth.ts`:
```typescript
describe('OAuth Module', () => {
  describe('resolvePath', () => {
    it('should expand ~ to home directory', () => {
      // Pure function test
    });
  });

  describe('loadOAuthKeys', () => {
    it('should load and parse oauth keys from file', () => {
      // Mock fs.existsSync and fs.readFileSync
    });
  });

  describe('refreshAccessToken', () => {
    it('should refresh token and save to disk', () => {
      // Mock oauth2Client.refreshAccessToken()
      // Mock fs.writeFileSync()
    });
  });
});
```

For `src/tools.ts`:
```typescript
describe('Tool Functions', () => {
  beforeEach(() => {
    // Mock getGmailClient
    vi.mock('./oauth', () => ({
      getGmailClient: vi.fn(),
    }));
  });

  describe('listMessages', () => {
    it('should list messages and enrich with metadata', () => {
      // Mock gmail.users.messages.list()
      // Mock gmail.users.messages.get()
    });
  });
});
```

**Integration Testing:**
- Use real Gmail sandbox or test account
- Run auth flow end-to-end
- Test actual API calls with real credentials

## Current Manual Testing Process

**Authentication:**
```bash
npm run auth
# Opens browser, completes OAuth flow
# Credentials saved to ~/.gmail-mcp/credentials.json
```

**Server Operation:**
```bash
npm run build
npm start
# Server listens on stdio
# Can be tested through MCP client
```

**Development:**
```bash
npm run dev
# TypeScript compiler in watch mode
# Auto-recompiles on changes
```

---

*Testing analysis: 2026-01-27*
