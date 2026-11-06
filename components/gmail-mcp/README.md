# Gmail MCP Server

A Model Context Protocol (MCP) server for Gmail with robust OAuth2 token refresh.

## Features

- **Reliable token refresh**: Automatically refreshes expired tokens without requiring restart
- **Full Gmail API access**: List, read, search, send, and manage emails
- **Label management**: Create and manage Gmail labels
- **Draft support**: Create and send drafts
- **Multi-account support**: Configure multiple accounts via environment variables

## Installation

### From Source (Recommended)

```bash
git clone https://github.com/technetcentral/gmail-mcp-server.git
cd gmail-mcp-server
npm install
npm run build
```

### Global Install (once published)

```bash
npm install -g @technetcentral/gmail-mcp-server
```

## Setup

### 1. Create Google Cloud OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Gmail API
4. Go to "APIs & Services" > "Credentials"
5. Click "Create Credentials" > "OAuth client ID"
6. Choose "Desktop app" as the application type
7. Download the JSON file and save it as `~/.gmail-mcp/gcp-oauth.keys.json`

### 2. Authenticate

```bash
npx gmail-mcp-server auth
```

This will open a browser window for Google authentication. After authorizing, your credentials will be saved to `~/.gmail-mcp/credentials.json`.

### 3. Configure MCP Client

#### OpenCode Configuration

Add to your `~/.config/opencode/opencode.jsonc`:

```jsonc
{
  "mcp": {
    "gmail": {
      "type": "local",
      "command": ["node", "/path/to/gmail-mcp/dist/index.js"],
      "environment": {
        "GMAIL_CREDENTIALS_PATH": "/Users/you/.gmail-mcp/credentials.json",
        "GMAIL_OAUTH_KEYS_PATH": "/Users/you/.gmail-mcp/gcp-oauth.keys.json"
      },
      "enabled": true
    }
  },
  "tools": {
    "gmail*": true
  }
}
```

#### Claude Desktop / Generic MCP Client

Add to your MCP config file (e.g., `.mcp.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gmail": {
      "command": "node",
      "args": ["/path/to/gmail-mcp/dist/index.js"],
      "env": {
        "GMAIL_CREDENTIALS_PATH": "~/.gmail-mcp/credentials.json",
        "GMAIL_OAUTH_KEYS_PATH": "~/.gmail-mcp/gcp-oauth.keys.json"
      }
    }
  }
}
```

### Multi-Account Setup

For multiple Gmail accounts, create separate server entries with different credential paths:

#### OpenCode Multi-Account

```jsonc
{
  "mcp": {
    "gmail-personal": {
      "type": "local",
      "command": ["node", "/path/to/gmail-mcp/dist/index.js"],
      "environment": {
        "GMAIL_CREDENTIALS_PATH": "/Users/you/.gmail-mcp/personal/credentials.json",
        "GMAIL_OAUTH_KEYS_PATH": "/Users/you/.gmail-mcp/gcp-oauth.keys.json"
      },
      "enabled": true
    },
    "gmail-work": {
      "type": "local",
      "command": ["node", "/path/to/gmail-mcp/dist/index.js"],
      "environment": {
        "GMAIL_CREDENTIALS_PATH": "/Users/you/.gmail-mcp/work/credentials.json",
        "GMAIL_OAUTH_KEYS_PATH": "/Users/you/.gmail-mcp/gcp-oauth.keys.json"
      },
      "enabled": true
    }
  },
  "tools": {
    "gmail-personal*": true,
    "gmail-work*": true
  }
}
```

#### Generic MCP Multi-Account

```json
{
  "mcpServers": {
    "gmail-personal": {
      "command": "node",
      "args": ["/path/to/gmail-mcp/dist/index.js"],
      "env": {
        "GMAIL_CREDENTIALS_PATH": "~/.gmail-mcp/personal/credentials.json",
        "GMAIL_OAUTH_KEYS_PATH": "~/.gmail-mcp/gcp-oauth.keys.json"
      }
    },
    "gmail-work": {
      "command": "node",
      "args": ["/path/to/gmail-mcp/dist/index.js"],
      "env": {
        "GMAIL_CREDENTIALS_PATH": "~/.gmail-mcp/work/credentials.json",
        "GMAIL_OAUTH_KEYS_PATH": "~/.gmail-mcp/gcp-oauth.keys.json"
      }
    }
  }
}
```

#### Authenticate Each Account

Run auth for each account by setting the credentials path:

```bash
# Personal account
GMAIL_CREDENTIALS_PATH=~/.gmail-mcp/personal/credentials.json npm run auth

# Work account  
GMAIL_CREDENTIALS_PATH=~/.gmail-mcp/work/credentials.json npm run auth
```

## Available Tools

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

## Gmail Search Syntax

The `search_messages` tool supports Gmail's search operators:

| Operator | Example | Description |
|----------|---------|-------------|
| `from:` | `from:user@example.com` | Messages from sender |
| `to:` | `to:me@example.com` | Messages to recipient |
| `subject:` | `subject:"meeting notes"` | Messages with subject text |
| `has:attachment` | `has:attachment` | Messages with attachments |
| `after:` | `after:2024/01/01` | Messages after date |
| `before:` | `before:2024/02/01` | Messages before date |
| `is:unread` | `is:unread` | Unread messages |
| `label:` | `label:work` | Messages with label |

Combine operators: `from:boss@company.com after:2024/01/01 has:attachment`

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GMAIL_CREDENTIALS_PATH` | Path to credentials.json | `~/.gmail-mcp/credentials.json` |
| `GMAIL_OAUTH_KEYS_PATH` | Path to OAuth keys | `~/.gmail-mcp/gcp-oauth.keys.json` |

## Development

```bash
# Install dependencies
npm install

# Build TypeScript
npm run build

# Watch mode for development
npm run dev

# Run the server
npm start

# Run authentication flow
npm run auth
```

## Project Structure

```
gmail-mcp/
├── src/
│   ├── index.ts      # MCP server entry point
│   ├── tools.ts      # Gmail API tool implementations
│   ├── oauth.ts      # OAuth2 client and token management
│   └── auth.ts       # Interactive authentication flow
├── dist/             # Compiled JavaScript
├── package.json
├── tsconfig.json
└── README.md
```

## License

MIT
