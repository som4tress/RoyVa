# Feature Specification: Broader Search Suggestions

## Overview

When a Gmail search returns zero results, the MCP server should include suggestions for broader search queries that might help the user find what they're looking for.

## Problem Statement

A user searched for `from:Don Stratton` but got no results. The email existed but was sent from `crownking62@yahoo.com` with "Don Stratton" mentioned only in the email body. The AI assistant had to manually suggest broadening the search to just `Stratton` (searching all fields) to find the email.

This manual intervention should be automated - when searches return empty results, the server should suggest broader alternatives.

## User Experience

### Current Behavior
```
User: Search for emails from Don Stratton
Server: { "messages": [] }
```

### Desired Behavior
```
User: Search for emails from Don Stratton
Server: {
  "messages": [],
  "suggestions": {
    "noResults": true,
    "broaderQueries": [
      {
        "query": "Stratton",
        "reason": "Search all fields for 'Stratton' instead of just the sender"
      },
      {
        "query": "Don",
        "reason": "Search all fields for 'Don' instead of just the sender"
      }
    ],
    "prompt": "No emails found matching 'from:Don Stratton'. Would you like me to try a broader search?"
  }
}
```

## Technical Specification

### Files to Modify

| File | Purpose |
|------|---------|
| `src/tools.ts` | Add query parsing and suggestion generation logic |

### Implementation Details

#### 1. Query Parser

Create a function to parse Gmail search queries into components:

```typescript
interface ParsedQuery {
  from?: string[];      // from: operator values
  to?: string[];        // to: operator values  
  subject?: string[];   // subject: operator values
  body?: string[];      // Plain text (searches body)
  after?: string;       // after: date
  before?: string;      // before: date
  hasAttachment?: boolean;
  label?: string[];
  isUnread?: boolean;
  raw: string;          // Original query string
}

function parseGmailQuery(query: string): ParsedQuery {
  // Parse operators: from:, to:, subject:, after:, before:, has:attachment, label:, is:unread
  // Handle quoted strings: from:"John Doe"
  // Remaining text is body search
}
```

#### 2. Suggestion Generator

Create a function to generate broader search suggestions:

```typescript
interface SearchSuggestion {
  query: string;
  reason: string;
}

interface SearchSuggestions {
  noResults: boolean;
  broaderQueries: SearchSuggestion[];
  prompt: string;
}

function generateBroaderSearchSuggestions(
  parsedQuery: ParsedQuery,
  originalQuery: string
): SearchSuggestions | null {
  // Only generate suggestions if there are restrictive operators
  // Suggestion strategies:
  // 1. Remove from:/to:/subject: and search all fields
  // 2. Remove date restrictions (after:/before:)
  // 3. Search individual words from multi-word names
  // 4. Remove label restrictions
}
```

#### 3. Suggestion Strategies

| Original Query Pattern | Suggested Broader Query | Reason |
|------------------------|------------------------|--------|
| `from:Don Stratton` | `Stratton` | Search all fields instead of just sender |
| `from:Don Stratton` | `Don` | Search for first name in all fields |
| `subject:invoice after:2025/01/01` | `subject:invoice` | Remove date restriction |
| `from:john@example.com label:work` | `from:john@example.com` | Remove label restriction |
| `"exact phrase" from:someone` | `"exact phrase"` | Remove sender restriction |

#### 4. Modified searchMessages Function

```typescript
export async function searchMessages(params: {
  query: string;
  maxResults?: number;
  pageToken?: string;
}): Promise<{
  messages: Array<{...}>;
  nextPageToken?: string;
  suggestions?: SearchSuggestions;
}> {
  const result = await listMessages({
    q: params.query,
    maxResults: params.maxResults,
    pageToken: params.pageToken,
  });

  // If no results, generate suggestions
  if (result.messages.length === 0) {
    const parsedQuery = parseGmailQuery(params.query);
    const suggestions = generateBroaderSearchSuggestions(parsedQuery, params.query);
    
    if (suggestions) {
      return {
        ...result,
        suggestions,
      };
    }
  }

  return result;
}
```

### Edge Cases

1. **Simple queries** - If the query is already simple (e.g., just `Stratton`), don't suggest anything
2. **Multiple operators** - Generate multiple suggestions, one for each operator removed
3. **Quoted strings** - Preserve quoted strings when extracting search terms
4. **Empty suggestions** - If no meaningful broader query can be generated, return null
5. **Date-only queries** - `after:2025/01/01 before:2025/02/01` should suggest expanding the date range

### Response Format

The `suggestions` field should only be present when:
1. The search returned zero results, AND
2. The query has operators that can be broadened

```typescript
// Zero results with suggestions
{
  "messages": [],
  "suggestions": {
    "noResults": true,
    "broaderQueries": [...],
    "prompt": "No emails found matching '...'. Would you like me to try a broader search?"
  }
}

// Zero results, simple query (no suggestions possible)
{
  "messages": []
}

// Results found (no suggestions needed)
{
  "messages": [...],
  "nextPageToken": "..."
}
```

## Testing

### Test Cases

1. `from:Don Stratton` returns no results → suggest `Stratton`, `Don`
2. `from:"John Doe" after:2025/01/01` returns no results → suggest without date, suggest without from
3. `meeting notes` returns no results → no suggestions (already broad)
4. `from:test@example.com` returns results → no suggestions needed
5. `subject:invoice label:finance after:2025/01/01` returns no results → multiple suggestions

### Manual Testing

1. Search for a name that exists only in email body, not sender field
2. Verify suggestions are generated
3. Execute suggested query and confirm it finds the email

## Future Enhancements

1. **Smart ranking** - Order suggestions by likelihood of success
2. **Spelling suggestions** - Suggest corrections for potential typos
3. **Interactive mode** - Allow user to select which suggestion to try
4. **Learning** - Track which suggestions lead to successful results

## Acceptance Criteria

- [ ] Zero-result searches with restrictive operators return suggestions
- [ ] Suggestions include both the broader query and a human-readable reason
- [ ] Simple queries (no operators) do not generate suggestions
- [ ] Successful searches do not include suggestions
- [ ] Query parser correctly handles quoted strings
- [ ] Query parser correctly handles all common Gmail operators
