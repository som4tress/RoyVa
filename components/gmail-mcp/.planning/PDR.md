# Project Design Record: @technetcentral/gmail-mcp-server

## Overview

A Model Context Protocol (MCP) server for Gmail with robust OAuth2 token refresh. This project replaces the buggy `@shinzolabs/gmail-mcp` server that fails to properly refresh expired OAuth tokens.

## Problem Statement

The existing `@shinzolabs/gmail-mcp` server has a critical bug where OAuth2 token refresh fails silently, requiring manual token refresh scripts and OpenCode restarts. This defeats the purpose of having refresh tokens and creates ongoing friction for users.

## Solution

Build a new Gmail MCP server from scratch with:
1. Proper OAuth2 token refresh that reads credentials fresh from disk on each request
2. Automatic token refresh when tokens expire (with 5-minute buffer)
3. Clear error messages when re-authentication is needed
4. Multi-account support via environment variables

## Project Location

`/Users/alvin/dev/mcp_servers/gmail-mcp/`

## Current State

The following files have been created but need finalization:
- `package.json` - needs name/repo URL update
- `tsconfig.json` - complete
- `src/oauth.ts` - OAuth2 implementation with proper token refresh
- `src/auth.ts` - CLI authentication flow (needs `open` package)
- `src/tools.ts` - Gmail API operations
- `src/index.ts` - MCP server entry point
- `README.md` - documentation

Dependencies installed: `@modelcontextprotocol/sdk`, `googleapis`

---

## User Stories

### US-1: Update Package Configuration
**As a** package maintainer  
**I want** the package.json to have correct metadata  
**So that** the package can be published to npm under the technetcentral org

**Acceptance Criteria:**
- [ ] Package name is `@technetcentral/gmail-mcp-server`
- [ ] Repository URL is `https://github.com/technetcentral/gmail-mcp-server`
- [ ] Binary name in `bin` field is `gmail-mcp-server`
- [ ] Author field is correctly set

**Implementation:**
Edit `/Users/alvin/dev/mcp_servers/gmail-mcp/package.json`:
```json
{
  "name": "@technetcentral/gmail-mcp-server",
  "bin": {
    "gmail-mcp-server": "dist/index.js"
  },
  "repository": {
    "type": "git",
    "url": "https://github.com/technetcentral/gmail-mcp-server"
  }
}
```

---

### US-2: Add Missing Dependencies
**As a** user authenticating for the first time  
**I want** the browser to open automatically during auth  
**So that** I don't have to manually copy/paste the URL

**Acceptance Criteria:**
- [ ] `open` package is added as a dependency
- [ ] Auth flow gracefully handles case where `open` is unavailable
- [ ] Auth URL is always printed to console as fallback

**Implementation:**
```bash
cd /Users/alvin/dev/mcp_servers/gmail-mcp && npm install open
```

---

### US-3: Build TypeScript Code
**As a** developer  
**I want** the TypeScript code compiled to JavaScript  
**So that** the MCP server can be executed

**Acceptance Criteria:**
- [ ] `npm run build` completes without errors
- [ ] `dist/` directory contains compiled `.js` files
- [ ] `dist/index.js` is executable

**Implementation:**
```bash
cd /Users/alvin/dev/mcp_servers/gmail-mcp && npm run build
```

---

### US-4: Initialize Git Repository
**As a** developer  
**I want** the project under version control  
**So that** changes can be tracked and pushed to GitHub

**Acceptance Criteria:**
- [ ] Git repository initialized
- [ ] `.gitignore` excludes: `node_modules/`, `dist/`, `*.log`, `.env`
- [ ] Initial commit with message: "Initial commit: Gmail MCP server with robust OAuth2 token refresh"
- [ ] All source files committed

**Implementation:**
1. Create `.gitignore`:
```
node_modules/
dist/
*.log
.env
.DS_Store
```

2. Initialize and commit:
```bash
cd /Users/alvin/dev/mcp_servers/gmail-mcp
git init
git add .
git commit -m "Initial commit: Gmail MCP server with robust OAuth2 token refresh"
```

---

### US-5: Configure MCP Client
**As a** user  
**I want** the new Gmail MCP server configured in my workspace  
**So that** I can use Gmail tools in OpenCode

**Acceptance Criteria:**
- [ ] `.mcp.json` in `/Users/alvin/dev/n8n_builder/` updated
- [ ] Two accounts configured: `gmail-lhc` and `gmail-personal`
- [ ] Uses existing credential paths at `~/.gmail-mcp/lhc/` and `~/.gmail-mcp/personal/`
- [ ] Uses local `node` command pointing to built `dist/index.js`

**Implementation:**
Update `/Users/alvin/dev/n8n_builder/.mcp.json` to add:
```json
{
  "mcpServers": {
    "n8n-mcp": { ... existing config ... },
    "gmail-lhc": {
      "command": "node",
      "args": ["/Users/alvin/dev/mcp_servers/gmail-mcp/dist/index.js"],
      "env": {
        "GMAIL_CREDENTIALS_PATH": "~/.gmail-mcp/lhc/credentials.json"
      }
    },
    "gmail-personal": {
      "command": "node",
      "args": ["/Users/alvin/dev/mcp_servers/gmail-mcp/dist/index.js"],
      "env": {
        "GMAIL_CREDENTIALS_PATH": "~/.gmail-mcp/personal/credentials.json"
      }
    }
  }
}
```

---

### US-6: Verify Token Refresh Works
**As a** user  
**I want** to confirm the OAuth2 token refresh works correctly  
**So that** I don't encounter the same issues as the old MCP server

**Acceptance Criteria:**
- [ ] After restarting OpenCode, Gmail tools are available
- [ ] `list_messages` tool returns recent emails without auth errors
- [ ] If token is expired, it auto-refreshes without requiring restart

**Verification Steps:**
1. Restart OpenCode to load new MCP config
2. Run: `list_messages` with `maxResults: 1` for LHC account
3. Check that email data is returned (not an auth error)

---

## Technical Notes

### OAuth2 Token Refresh Logic (Key Fix)

The core fix in `src/oauth.ts` ensures tokens are always read fresh from disk:

```typescript
export async function getAuthenticatedClient(): Promise<Auth.OAuth2Client> {
  // ALWAYS load fresh credentials from disk (not cached in memory)
  const credentials = loadCredentials();
  
  // Check expiry with 5-minute buffer
  const isExpired = credentials.expiry_date < Date.now() + (5 * 60 * 1000);
  
  if (isExpired) {
    // Refresh and SAVE to disk immediately
    validCredentials = await refreshAccessToken(oauth2Client, credentials);
  }
  
  // Set all credentials on client
  oauth2Client.setCredentials({
    access_token: validCredentials.access_token,
    refresh_token: validCredentials.refresh_token,
    expiry_date: validCredentials.expiry_date,
  });
  
  return oauth2Client;
}
```

### Existing Credential Locations

| Account | Credentials Path |
|---------|------------------|
| LHC | `~/.gmail-mcp/lhc/credentials.json` |
| Personal | `~/.gmail-mcp/personal/credentials.json` |
| OAuth Keys | `~/.gmail-mcp/gcp-oauth.keys.json` |

These credentials were created with the old MCP server and are compatible - no re-authentication needed.

### Available Tools (Already Implemented)

| Tool | Description |
|------|-------------|
| `list_messages` | List messages in inbox or by label |
| `read_message` | Read full email content |
| `search_messages` | Search using Gmail query syntax |
| `send_message` | Send a new email |
| `modify_message` | Add/remove labels, mark read/unread |
| `list_labels` | List all Gmail labels |
| `create_label` | Create a new label |
| `create_draft` | Create a draft email |
| `send_draft` | Send an existing draft |

---

## Execution Order

1. **US-1**: Update package.json metadata
2. **US-2**: Add `open` dependency
3. **US-3**: Build TypeScript
4. **US-4**: Initialize git repo
5. **US-5**: Update .mcp.json config
6. **US-6**: Verify (requires OpenCode restart)

---

## Future Work (Out of Scope for This Phase)

- Create GitHub repository at technetcentral/gmail-mcp-server
- Push code to GitHub
- Publish to npm registry
- Add attachment support
- Add thread/conversation tools
- Add filter management tools
