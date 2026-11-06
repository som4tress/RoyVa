# Requirements: @technetcentral/gmail-mcp-server

**Defined:** 2026-01-27
**Core Value:** OAuth2 tokens refresh automatically and transparently

## v1 Requirements

### Package Configuration

- [x] **PKG-01**: Package name is `@technetcentral/gmail-mcp-server`
- [x] **PKG-02**: Repository URL points to `https://github.com/technetcentral/gmail-mcp-server`
- [x] **PKG-03**: Binary name in `bin` field is `gmail-mcp-server`

### Dependencies

- [x] **DEP-01**: `open` package installed for browser auto-launch during auth

### Build

- [x] **BLD-01**: TypeScript compiles without errors via `npm run build`
- [x] **BLD-02**: `dist/` directory contains compiled `.js` files

### Version Control

- [x] **GIT-01**: Git repository initialized
- [x] **GIT-02**: `.gitignore` excludes node_modules/, dist/, *.log, .env
- [x] **GIT-03**: All source files committed

### MCP Client Configuration

- [x] **MCP-01**: Gmail MCP server configured in `/Users/alvin/dev/n8n_builder/.mcp.json`
- [x] **MCP-02**: Two accounts configured: `gmail-lhc` and `gmail-personal`
- [x] **MCP-03**: Uses existing credential paths at `~/.gmail-mcp/lhc/` and `~/.gmail-mcp/personal/`

### Verification

- [ ] **VER-01**: Gmail tools available after OpenCode restart
- [ ] **VER-02**: `list_messages` returns recent emails without auth errors

### Broader Search Suggestions

- [ ] **BSS-01**: Query parser correctly parses Gmail search operators (from:, to:, subject:, after:, before:, has:, label:, is:)
- [ ] **BSS-02**: Query parser correctly handles quoted strings (e.g., `from:"John Doe"`)
- [ ] **BSS-03**: Suggestion generator returns broader queries when restrictive operators produce no results
- [ ] **BSS-04**: Simple queries (no operators) do not generate suggestions

## Out of Scope

| Feature | Reason |
|---------|--------|
| GitHub repo creation | Future work after local verification |
| npm publishing | Future work after GitHub push |
| Attachment downloads | Future feature |
| Thread/conversation tools | Future feature |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PKG-01 | Phase 1 | Complete |
| PKG-02 | Phase 1 | Complete |
| PKG-03 | Phase 1 | Complete |
| DEP-01 | Phase 1 | Complete |
| BLD-01 | Phase 1 | Complete |
| BLD-02 | Phase 1 | Complete |
| GIT-01 | Phase 1 | Complete |
| GIT-02 | Phase 1 | Complete |
| GIT-03 | Phase 1 | Complete |
| MCP-01 | Phase 1 | Complete |
| MCP-02 | Phase 1 | Complete |
| MCP-03 | Phase 1 | Complete |
| VER-01 | Phase 6 | Pending |
| VER-02 | Phase 6 | Pending |
| BSS-01 | Phase 7 | Pending |
| BSS-02 | Phase 7 | Pending |
| BSS-03 | Phase 7 | Pending |
| BSS-04 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓

---
*Requirements defined: 2026-01-27*
