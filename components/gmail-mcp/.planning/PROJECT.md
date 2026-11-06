# @technetcentral/gmail-mcp-server

## What This Is

A Model Context Protocol (MCP) server for Gmail with robust OAuth2 token refresh. Replaces the buggy `@shinzolabs/gmail-mcp` server that fails to properly refresh expired OAuth tokens, requiring manual intervention and restarts.

## Core Value

OAuth2 tokens refresh automatically and transparently — credentials are always read fresh from disk, refreshed when expired (with 5-minute buffer), and saved immediately.

## Requirements

### Validated

- ✓ OAuth2 authentication flow with Google — existing (`src/oauth.ts`, `src/auth.ts`)
- ✓ Gmail API operations (list, read, search, send, modify, labels, drafts) — existing (`src/tools.ts`)
- ✓ MCP server with stdio transport — existing (`src/index.ts`)
- ✓ Automatic token refresh with disk persistence — existing (`src/oauth.ts`)
- ✓ Multi-account support via environment variables — existing

### Active

- [ ] Package metadata configured for npm publishing (@technetcentral org)
- [ ] Browser auto-opens during OAuth flow (open package)
- [ ] TypeScript compiles without errors
- [ ] Git repository initialized with proper .gitignore
- [ ] MCP client configured in n8n_builder workspace
- [ ] Token refresh verified working end-to-end

### Out of Scope

- GitHub repository creation — future work
- npm publishing — future work
- Attachment download support — future work
- Thread/conversation tools — future work

## Context

**Existing code**: 4 TypeScript files in `src/` implementing full functionality
- `oauth.ts` — OAuth2 client, credential management, token refresh (the key fix)
- `auth.ts` — CLI authentication flow with local callback server
- `tools.ts` — Gmail API operations (9 tools)
- `index.ts` — MCP server entry point

**Dependencies installed**: `@modelcontextprotocol/sdk`, `googleapis`

**Credential locations**:
- LHC account: `~/.gmail-mcp/lhc/credentials.json`
- Personal account: `~/.gmail-mcp/personal/credentials.json`
- OAuth keys: `~/.gmail-mcp/gcp-oauth.keys.json`

## Constraints

- **Compatibility**: Must work with existing credentials from old MCP server (no re-auth needed)
- **Environment**: Node.js 18+, macOS development

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Read credentials fresh from disk each request | Prevents stale token issues that plagued old server | — Pending |
| 5-minute expiry buffer for refresh | Ensures tokens are refreshed before they actually expire | — Pending |

---
*Last updated: 2026-01-27 after initialization*
