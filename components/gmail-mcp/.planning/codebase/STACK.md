# Technology Stack

**Analysis Date:** 2026-01-27

## Languages

**Primary:**
- TypeScript 5.x - Full codebase, all source files in `src/` compiled to JavaScript

## Runtime

**Environment:**
- Node.js 18+ (specified in `package.json` engines field)

**Package Manager:**
- npm
- Lockfile: `package-lock.json` present

## Frameworks

**Core:**
- Model Context Protocol (MCP) SDK v1.0.0 - Server implementation via `@modelcontextprotocol/sdk`
- Google APIs JavaScript Client Library v144.0.0 - Gmail API interaction

**Build/Dev:**
- TypeScript 5.x - Compilation and type checking
- Node built-in modules - `http`, `fs`, `path`, `os`, `url`

## Key Dependencies

**Critical:**
- `@modelcontextprotocol/sdk` v1.0.0 - MCP server framework and stdio transport (`src/index.ts`)
- `googleapis` v144.0.0 - Google OAuth2 and Gmail API client library (`src/oauth.ts`, `src/tools.ts`)

**Development:**
- `@types/node` v20.x - TypeScript type definitions for Node.js
- `typescript` v5.x - TypeScript compiler

## Configuration

**TypeScript:**
- Config file: `tsconfig.json`
- Target: ES2022
- Module: NodeNext with NodeNext module resolution
- Output: `./dist` directory
- Source: `./src/**/*`
- Strict mode: Enabled
- Declarations: Enabled (`declaration: true`)

**Build Scripts:**
```json
"build": "tsc"           // Compile TypeScript to JavaScript
"dev": "tsc --watch"     // Watch mode for development
"start": "node dist/index.js"  // Run the MCP server
"auth": "node dist/auth.js"    // OAuth authentication flow
```

## Platform Requirements

**Development:**
- Node.js 18 or higher
- npm for dependency management
- TypeScript build tools (installed via npm)

**Production:**
- Node.js 18+ runtime
- Credentials file: `~/.gmail-mcp/credentials.json` (environment-configurable)
- OAuth keys file: `~/.gmail-mcp/gcp-oauth.keys.json` (environment-configurable)

**Deployment Target:**
- Runs as a standalone Node.js process
- Communicates via stdio (standard input/output) for MCP protocol
- Can be installed globally via npm: `npm install -g gmail-mcp-server`

---

*Stack analysis: 2026-01-27*
