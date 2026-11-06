import { gmail_v1 } from "googleapis";
import { getGmailClient } from "./oauth.js";

type Gmail = gmail_v1.Gmail;

/**
 * Parsed Gmail query components
 */
interface ParsedQuery {
  from?: string[];
  to?: string[];
  subject?: string[];
  body?: string[];
  after?: string;
  before?: string;
  hasAttachment?: boolean;
  label?: string[];
  isUnread?: boolean;
  raw: string;
}

/**
 * A single search suggestion
 */
interface SearchSuggestion {
  query: string;
  reason: string;
}

/**
 * Search suggestions for zero-result queries
 */
interface SearchSuggestions {
  noResults: boolean;
  broaderQueries: SearchSuggestion[];
  prompt: string;
}

/**
 * Decodes base64url encoded content
 */
function decodeBase64Url(data: string): string {
  const base64 = data.replace(/-/g, "+").replace(/_/g, "/");
  return Buffer.from(base64, "base64").toString("utf-8");
}

/**
 * Extracts the body content from a message payload
 */
function extractBody(payload: gmail_v1.Schema$MessagePart): { text: string; html: string } {
  let text = "";
  let html = "";

  function processPayload(part: gmail_v1.Schema$MessagePart): void {
    if (part.body?.data) {
      const content = decodeBase64Url(part.body.data);
      if (part.mimeType === "text/plain") {
        text = content;
      } else if (part.mimeType === "text/html") {
        html = content;
      }
    }

    if (part.parts) {
      for (const subPart of part.parts) {
        processPayload(subPart);
      }
    }
  }

  processPayload(payload);
  return { text, html };
}

/**
 * Gets a header value from a message
 */
function getHeader(headers: gmail_v1.Schema$MessagePartHeader[] | undefined, name: string): string {
  if (!headers) return "";
  const header = headers.find((h) => h.name?.toLowerCase() === name.toLowerCase());
  return header?.value || "";
}

/**
 * List messages in the mailbox
 */
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
  const gmail = await getGmailClient();

  const response = await gmail.users.messages.list({
    userId: "me",
    maxResults: params.maxResults || 20,
    labelIds: params.labelIds,
    q: params.q,
    pageToken: params.pageToken,
  });

  const messages = [];

  if (response.data.messages) {
    for (const msg of response.data.messages) {
      const detail = await gmail.users.messages.get({
        userId: "me",
        id: msg.id!,
        format: "metadata",
        metadataHeaders: ["From", "Subject", "Date"],
      });

      messages.push({
        id: msg.id!,
        threadId: msg.threadId!,
        snippet: detail.data.snippet || "",
        from: getHeader(detail.data.payload?.headers, "From"),
        subject: getHeader(detail.data.payload?.headers, "Subject"),
        date: getHeader(detail.data.payload?.headers, "Date"),
        labelIds: detail.data.labelIds || [],
      });
    }
  }

  return {
    messages,
    nextPageToken: response.data.nextPageToken || undefined,
  };
}

/**
 * Read a specific message
 */
export async function readMessage(params: {
  messageId: string;
}): Promise<{
  id: string;
  threadId: string;
  from: string;
  to: string;
  cc: string;
  subject: string;
  date: string;
  body: string;
  htmlBody: string;
  labelIds: string[];
  attachments: Array<{
    filename: string;
    mimeType: string;
    size: number;
    attachmentId: string;
  }>;
}> {
  const gmail = await getGmailClient();

  const response = await gmail.users.messages.get({
    userId: "me",
    id: params.messageId,
    format: "full",
  });

  const headers = response.data.payload?.headers;
  const { text, html } = extractBody(response.data.payload!);

  // Extract attachments
  const attachments: Array<{
    filename: string;
    mimeType: string;
    size: number;
    attachmentId: string;
  }> = [];

  function findAttachments(part: gmail_v1.Schema$MessagePart): void {
    if (part.filename && part.body?.attachmentId) {
      attachments.push({
        filename: part.filename,
        mimeType: part.mimeType || "application/octet-stream",
        size: part.body.size || 0,
        attachmentId: part.body.attachmentId,
      });
    }
    if (part.parts) {
      for (const subPart of part.parts) {
        findAttachments(subPart);
      }
    }
  }

  if (response.data.payload) {
    findAttachments(response.data.payload);
  }

  return {
    id: response.data.id!,
    threadId: response.data.threadId!,
    from: getHeader(headers, "From"),
    to: getHeader(headers, "To"),
    cc: getHeader(headers, "Cc"),
    subject: getHeader(headers, "Subject"),
    date: getHeader(headers, "Date"),
    body: text,
    htmlBody: html,
    labelIds: response.data.labelIds || [],
    attachments,
  };
}

/**
 * Parses a Gmail search query into structured components
 * Handles operators: from:, to:, subject:, after:, before:, has:, label:, is:
 * Supports quoted values: from:"John Doe"
 */
function parseGmailQuery(query: string): ParsedQuery {
  const result: ParsedQuery = { raw: query };
  
  // Regex: captures operator name and either "quoted value" or unquoted-value
  const operatorRegex = /(\w+):(?:"([^"]+)"|(\S+))/gi;
  
  let match: RegExpExecArray | null;
  const matchedRanges: Array<[number, number]> = [];
  
  while ((match = operatorRegex.exec(query)) !== null) {
    const operator = match[1].toLowerCase();
    const value = match[2] || match[3]; // Quoted takes precedence
    
    if (!value) continue; // Skip empty values
    
    matchedRanges.push([match.index, match.index + match[0].length]);
    
    switch (operator) {
      case 'from':
        (result.from ??= []).push(value);
        break;
      case 'to':
        (result.to ??= []).push(value);
        break;
      case 'subject':
        (result.subject ??= []).push(value);
        break;
      case 'after':
        result.after = value;
        break;
      case 'before':
        result.before = value;
        break;
      case 'has':
        if (value.toLowerCase() === 'attachment') {
          result.hasAttachment = true;
        }
        break;
      case 'label':
        (result.label ??= []).push(value);
        break;
      case 'is':
        if (value.toLowerCase() === 'unread') {
          result.isUnread = true;
        }
        break;
    }
  }
  
  // Extract remaining text (body search terms)
  matchedRanges.sort((a, b) => b[0] - a[0]);
  let remaining = query;
  for (const [start, end] of matchedRanges) {
    remaining = remaining.slice(0, start) + remaining.slice(end);
  }
  remaining = remaining.trim();
  
  if (remaining) {
    const bodyTerms: string[] = [];
    const phraseRegex = /"([^"]+)"|(\S+)/g;
    let bodyMatch: RegExpExecArray | null;
    while ((bodyMatch = phraseRegex.exec(remaining)) !== null) {
      bodyTerms.push(bodyMatch[1] || bodyMatch[2]);
    }
    if (bodyTerms.length > 0) {
      result.body = bodyTerms;
    }
  }
  
  return result;
}

/**
 * Generates broader search suggestions for a parsed query
 * Returns null if query has no operators (already broad) or no suggestions possible
 */
function generateBroaderSuggestions(parsed: ParsedQuery): SearchSuggestions | null {
  // BSS-04: Simple queries (no operators) do not generate suggestions
  const hasOperators = !!(
    parsed.from?.length ||
    parsed.to?.length ||
    parsed.subject?.length ||
    parsed.after ||
    parsed.before ||
    parsed.hasAttachment ||
    parsed.label?.length ||
    parsed.isUnread
  );
  
  if (!hasOperators) {
    return null;
  }
  
  const suggestions: SearchSuggestion[] = [];
  
  // Strategy 1: Extract words from field-specific operators and search all fields
  const fieldOperators: Array<{ field: string[]; name: string }> = [
    { field: parsed.from || [], name: 'sender' },
    { field: parsed.to || [], name: 'recipient' },
    { field: parsed.subject || [], name: 'subject' },
  ];
  
  for (const { field, name } of fieldOperators) {
    for (const value of field) {
      const words = value.split(/\s+/).filter(w => w.length > 2);
      for (const word of words) {
        suggestions.push({
          query: word,
          reason: `Search all fields for "${word}" instead of just the ${name}`
        });
      }
      // Multi-word values: also suggest full phrase
      if (words.length > 1) {
        suggestions.push({
          query: `"${value}"`,
          reason: `Search all fields for "${value}" as a phrase`
        });
      }
    }
  }
  
  // Strategy 2: Remove date restrictions
  if (parsed.after || parsed.before) {
    const parts: string[] = [];
    if (parsed.from) parts.push(...parsed.from.map(v => `from:${v.includes(' ') ? `"${v}"` : v}`));
    if (parsed.to) parts.push(...parsed.to.map(v => `to:${v.includes(' ') ? `"${v}"` : v}`));
    if (parsed.subject) parts.push(...parsed.subject.map(v => `subject:${v.includes(' ') ? `"${v}"` : v}`));
    if (parsed.body) parts.push(...parsed.body);
    if (parsed.label) parts.push(...parsed.label.map(v => `label:${v}`));
    
    if (parts.length > 0) {
      suggestions.push({
        query: parts.join(' '),
        reason: 'Remove date restrictions to search all time'
      });
    }
  }
  
  // Strategy 3: Remove label restrictions
  if (parsed.label?.length) {
    const parts: string[] = [];
    if (parsed.from) parts.push(...parsed.from.map(v => `from:${v.includes(' ') ? `"${v}"` : v}`));
    if (parsed.to) parts.push(...parsed.to.map(v => `to:${v.includes(' ') ? `"${v}"` : v}`));
    if (parsed.subject) parts.push(...parsed.subject.map(v => `subject:${v.includes(' ') ? `"${v}"` : v}`));
    if (parsed.body) parts.push(...parsed.body);
    if (parsed.after) parts.push(`after:${parsed.after}`);
    if (parsed.before) parts.push(`before:${parsed.before}`);
    
    if (parts.length > 0) {
      suggestions.push({
        query: parts.join(' '),
        reason: 'Search all labels instead of specific ones'
      });
    }
  }
  
  if (suggestions.length === 0) {
    return null;
  }
  
  // Deduplicate and limit to 5 suggestions
  const seen = new Set<string>();
  const uniqueSuggestions = suggestions.filter(s => {
    if (seen.has(s.query)) return false;
    seen.add(s.query);
    return true;
  }).slice(0, 5);
  
  return {
    noResults: true,
    broaderQueries: uniqueSuggestions,
    prompt: `No emails found matching "${parsed.raw}". Would you like me to try a broader search?`
  };
}

/**
 * Search messages using Gmail query syntax
 * Returns suggestions for broader queries if search returns zero results
 */
export async function searchMessages(params: {
  query: string;
  maxResults?: number;
  pageToken?: string;
}): Promise<{
  messages: Array<{
    id: string;
    threadId: string;
    snippet: string;
    from: string;
    subject: string;
    date: string;
  }>;
  nextPageToken?: string;
  suggestions?: SearchSuggestions;
}> {
  const result = await listMessages({
    q: params.query,
    maxResults: params.maxResults,
    pageToken: params.pageToken,
  });

  // Only generate suggestions if no results
  if (result.messages.length === 0) {
    const parsed = parseGmailQuery(params.query);
    const suggestions = generateBroaderSuggestions(parsed);
    
    if (suggestions) {
      return {
        messages: result.messages.map(m => ({
          id: m.id,
          threadId: m.threadId,
          snippet: m.snippet,
          from: m.from,
          subject: m.subject,
          date: m.date,
        })),
        nextPageToken: result.nextPageToken,
        suggestions,
      };
    }
  }

  return {
    messages: result.messages.map(m => ({
      id: m.id,
      threadId: m.threadId,
      snippet: m.snippet,
      from: m.from,
      subject: m.subject,
      date: m.date,
    })),
    nextPageToken: result.nextPageToken,
  };
}

/**
 * Send an email
 */
export async function sendMessage(params: {
  to: string;
  subject: string;
  body: string;
  cc?: string;
  bcc?: string;
  threadId?: string;
}): Promise<{ id: string; threadId: string }> {
  const gmail = await getGmailClient();

  // Build RFC 2822 formatted email
  const messageParts = [
    `To: ${params.to}`,
    `Subject: ${params.subject}`,
    "Content-Type: text/plain; charset=utf-8",
    "MIME-Version: 1.0",
  ];

  if (params.cc) {
    messageParts.splice(1, 0, `Cc: ${params.cc}`);
  }

  if (params.bcc) {
    messageParts.splice(1, 0, `Bcc: ${params.bcc}`);
  }

  messageParts.push("", params.body);

  const message = messageParts.join("\r\n");
  const encodedMessage = Buffer.from(message)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

  const response = await gmail.users.messages.send({
    userId: "me",
    requestBody: {
      raw: encodedMessage,
      threadId: params.threadId,
    },
  });

  return {
    id: response.data.id!,
    threadId: response.data.threadId!,
  };
}

/**
 * Modify message labels
 */
export async function modifyMessage(params: {
  messageId: string;
  addLabelIds?: string[];
  removeLabelIds?: string[];
}): Promise<{ id: string; labelIds: string[] }> {
  const gmail = await getGmailClient();

  const response = await gmail.users.messages.modify({
    userId: "me",
    id: params.messageId,
    requestBody: {
      addLabelIds: params.addLabelIds,
      removeLabelIds: params.removeLabelIds,
    },
  });

  return {
    id: response.data.id!,
    labelIds: response.data.labelIds || [],
  };
}

/**
 * List all labels
 */
export async function listLabels(): Promise<
  Array<{
    id: string;
    name: string;
    type: string;
    messageListVisibility?: string;
    labelListVisibility?: string;
  }>
> {
  const gmail = await getGmailClient();

  const response = await gmail.users.labels.list({
    userId: "me",
  });

  return (response.data.labels || []).map((label) => ({
    id: label.id!,
    name: label.name!,
    type: label.type!,
    messageListVisibility: label.messageListVisibility || undefined,
    labelListVisibility: label.labelListVisibility || undefined,
  }));
}

/**
 * Create a new label
 */
export async function createLabel(params: {
  name: string;
  messageListVisibility?: "show" | "hide";
  labelListVisibility?: "labelShow" | "labelShowIfUnread" | "labelHide";
}): Promise<{
  id: string;
  name: string;
}> {
  const gmail = await getGmailClient();

  const response = await gmail.users.labels.create({
    userId: "me",
    requestBody: {
      name: params.name,
      messageListVisibility: params.messageListVisibility,
      labelListVisibility: params.labelListVisibility,
    },
  });

  return {
    id: response.data.id!,
    name: response.data.name!,
  };
}

/**
 * Create a draft
 */
export async function createDraft(params: {
  to: string;
  subject: string;
  body: string;
  cc?: string;
  bcc?: string;
  threadId?: string;
}): Promise<{ id: string; messageId: string }> {
  const gmail = await getGmailClient();

  // Build RFC 2822 formatted email
  const messageParts = [
    `To: ${params.to}`,
    `Subject: ${params.subject}`,
    "Content-Type: text/plain; charset=utf-8",
    "MIME-Version: 1.0",
  ];

  if (params.cc) {
    messageParts.splice(1, 0, `Cc: ${params.cc}`);
  }

  if (params.bcc) {
    messageParts.splice(1, 0, `Bcc: ${params.bcc}`);
  }

  messageParts.push("", params.body);

  const message = messageParts.join("\r\n");
  const encodedMessage = Buffer.from(message)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

  const response = await gmail.users.drafts.create({
    userId: "me",
    requestBody: {
      message: {
        raw: encodedMessage,
        threadId: params.threadId,
      },
    },
  });

  return {
    id: response.data.id!,
    messageId: response.data.message?.id || "",
  };
}

/**
 * Send an existing draft
 */
export async function sendDraft(params: {
  draftId: string;
}): Promise<{ id: string; threadId: string }> {
  const gmail = await getGmailClient();

  const response = await gmail.users.drafts.send({
    userId: "me",
    requestBody: {
      id: params.draftId,
    },
  });

  return {
    id: response.data.id!,
    threadId: response.data.threadId!,
  };
}
