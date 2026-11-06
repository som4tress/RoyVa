#!/usr/bin/env node

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
  searchMessages,
  sendMessage,
  modifyMessage,
  listLabels,
  createLabel,
  createDraft,
  sendDraft,
} from "./tools.js";

// Tool definitions
const tools = [
  {
    name: "list_messages",
    description: "List messages in the Gmail inbox or specified labels",
    inputSchema: {
      type: "object" as const,
      properties: {
        maxResults: {
          type: "number",
          description: "Maximum number of messages to return (default: 20, max: 100)",
        },
        labelIds: {
          type: "array",
          items: { type: "string" },
          description: "Filter by label IDs (e.g., ['INBOX', 'UNREAD'])",
        },
        q: {
          type: "string",
          description: "Gmail search query (e.g., 'from:example@gmail.com')",
        },
        pageToken: {
          type: "string",
          description: "Token for pagination",
        },
      },
    },
  },
  {
    name: "read_message",
    description: "Read the full content of a specific email message",
    inputSchema: {
      type: "object" as const,
      properties: {
        messageId: {
          type: "string",
          description: "The ID of the message to read",
        },
      },
      required: ["messageId"],
    },
  },
  {
    name: "search_messages",
    description: "Search for messages using Gmail search syntax",
    inputSchema: {
      type: "object" as const,
      properties: {
        query: {
          type: "string",
          description: "Gmail search query (e.g., 'from:user@example.com after:2024/01/01 has:attachment')",
        },
        maxResults: {
          type: "number",
          description: "Maximum number of results (default: 20)",
        },
        pageToken: {
          type: "string",
          description: "Token for pagination",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "send_message",
    description: "Send a new email message",
    inputSchema: {
      type: "object" as const,
      properties: {
        to: {
          type: "string",
          description: "Recipient email address",
        },
        subject: {
          type: "string",
          description: "Email subject",
        },
        body: {
          type: "string",
          description: "Email body (plain text)",
        },
        cc: {
          type: "string",
          description: "CC recipients (comma-separated)",
        },
        bcc: {
          type: "string",
          description: "BCC recipients (comma-separated)",
        },
        threadId: {
          type: "string",
          description: "Thread ID to reply to",
        },
      },
      required: ["to", "subject", "body"],
    },
  },
  {
    name: "modify_message",
    description: "Modify labels on a message (add/remove labels, mark read/unread)",
    inputSchema: {
      type: "object" as const,
      properties: {
        messageId: {
          type: "string",
          description: "The ID of the message to modify",
        },
        addLabelIds: {
          type: "array",
          items: { type: "string" },
          description: "Label IDs to add (e.g., ['STARRED', 'IMPORTANT'])",
        },
        removeLabelIds: {
          type: "array",
          items: { type: "string" },
          description: "Label IDs to remove (e.g., ['UNREAD'])",
        },
      },
      required: ["messageId"],
    },
  },
  {
    name: "list_labels",
    description: "List all Gmail labels (system and user-created)",
    inputSchema: {
      type: "object" as const,
      properties: {},
    },
  },
  {
    name: "create_label",
    description: "Create a new Gmail label",
    inputSchema: {
      type: "object" as const,
      properties: {
        name: {
          type: "string",
          description: "Name for the new label",
        },
        messageListVisibility: {
          type: "string",
          enum: ["show", "hide"],
          description: "Whether to show messages with this label in the message list",
        },
        labelListVisibility: {
          type: "string",
          enum: ["labelShow", "labelShowIfUnread", "labelHide"],
          description: "How the label appears in the label list",
        },
      },
      required: ["name"],
    },
  },
  {
    name: "create_draft",
    description: "Create a draft email (not sent)",
    inputSchema: {
      type: "object" as const,
      properties: {
        to: {
          type: "string",
          description: "Recipient email address",
        },
        subject: {
          type: "string",
          description: "Email subject",
        },
        body: {
          type: "string",
          description: "Email body (plain text)",
        },
        cc: {
          type: "string",
          description: "CC recipients (comma-separated)",
        },
        bcc: {
          type: "string",
          description: "BCC recipients (comma-separated)",
        },
        threadId: {
          type: "string",
          description: "Thread ID to associate the draft with",
        },
      },
      required: ["to", "subject", "body"],
    },
  },
  {
    name: "send_draft",
    description: "Send an existing draft",
    inputSchema: {
      type: "object" as const,
      properties: {
        draftId: {
          type: "string",
          description: "The ID of the draft to send",
        },
      },
      required: ["draftId"],
    },
  },
];

// Create server
const server = new Server(
  {
    name: "gmail-mcp-server",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Handle list tools request
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    let result: unknown;

    switch (name) {
      case "list_messages":
        result = await listMessages(args as Parameters<typeof listMessages>[0]);
        break;

      case "read_message":
        result = await readMessage(args as Parameters<typeof readMessage>[0]);
        break;

      case "search_messages":
        result = await searchMessages(args as Parameters<typeof searchMessages>[0]);
        break;

      case "send_message":
        result = await sendMessage(args as Parameters<typeof sendMessage>[0]);
        break;

      case "modify_message":
        result = await modifyMessage(args as Parameters<typeof modifyMessage>[0]);
        break;

      case "list_labels":
        result = await listLabels();
        break;

      case "create_label":
        result = await createLabel(args as Parameters<typeof createLabel>[0]);
        break;

      case "create_draft":
        result = await createDraft(args as Parameters<typeof createDraft>[0]);
        break;

      case "send_draft":
        result = await sendDraft(args as Parameters<typeof sendDraft>[0]);
        break;

      default:
        return {
          content: [{ type: "text", text: `Unknown tool: ${name}` }],
          isError: true,
        };
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
});

// Start server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Gmail MCP server running on stdio");
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
