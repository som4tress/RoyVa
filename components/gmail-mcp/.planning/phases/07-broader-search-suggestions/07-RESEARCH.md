# Phase 7: Broader Search Suggestions - Research

**Researched:** 2026-01-29
**Domain:** Gmail query parsing and search suggestion generation
**Confidence:** HIGH

## Summary

This phase involves parsing Gmail search queries and generating broader alternatives when searches return no results. The research covers two key areas: (1) how to parse Gmail's query syntax, and (2) how to generate useful broader suggestions.

**Key finding:** For this specific use case, a lightweight hand-rolled parser is recommended over external libraries. The `search-query-parser` npm package (last updated 2021, 13 open issues) supports Gmail-like syntax but requires configuration for Gmail's specific operators and doesn't handle all Gmail edge cases (like `is:`, `has:`, `in:` operators). Given the bounded scope (8-10 specific operators) and the need for Gmail-specific logic, a focused ~50-line TypeScript parser is more maintainable, has zero dependencies, and can be precisely tuned to Gmail's documented syntax.

**Primary recommendation:** Hand-roll a simple regex-based parser targeting Gmail's documented operators, extracting values into a typed `ParsedQuery` interface for suggestion generation.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Built-in TypeScript/JS | N/A | Regex-based parsing | Zero dependencies, full control, exact Gmail operator support |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `search-query-parser` | 1.6.0 | Generic query parsing | Only if requirements expand beyond Gmail operators (NOT recommended for this feature) |
| `@muhgholy/search-query-parser` | 3.0.0 | Gmail-like syntax parsing | Alternative if full query manipulation needed (NOT recommended) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled parser | `search-query-parser` | Library: More features but last updated 2021, 13 open issues, requires keyword configuration, doesn't natively handle Gmail's `is:`, `has:`, `in:` operators |
| Hand-rolled parser | Full parsing library (PEG.js, nearley) | Overkill - we're extracting values, not building AST |

**Installation:**
```bash
# No additional dependencies needed
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── tools.ts           # Add parseGmailQuery() and generateBroaderSuggestions()
└── (existing files)   # No new files needed
```

**Rationale:** Keep all search-related logic in `tools.ts` where `searchMessages` already lives. No need for separate modules given the small scope (~100 lines total).

### Pattern 1: Regex-Based Operator Extraction
**What:** Use a single regex to extract all `operator:value` pairs, then categorize by operator name
**When to use:** Bounded set of known operators (Gmail has ~20, we need ~8)
**Example:**
```typescript
// Source: Gmail official docs + verified pattern
interface ParsedQuery {
  from?: string[];
  to?: string[];
  subject?: string[];
  body?: string[];      // Plain text without operators
  after?: string;
  before?: string;
  hasAttachment?: boolean;
  label?: string[];
  isUnread?: boolean;
  raw: string;
}

function parseGmailQuery(query: string): ParsedQuery {
  const result: ParsedQuery = { raw: query };
  
  // Match operator:value or operator:"quoted value" patterns
  // Gmail uses: from:, to:, subject:, after:, before:, has:, label:, is:
  const operatorRegex = /(\w+):(?:"([^"]+)"|(\S+))/g;
  
  let match: RegExpExecArray | null;
  let remainingQuery = query;
  
  while ((match = operatorRegex.exec(query)) !== null) {
    const operator = match[1].toLowerCase();
    const value = match[2] || match[3]; // Quoted or unquoted
    
    // Remove matched operator from remaining query
    remainingQuery = remainingQuery.replace(match[0], '').trim();
    
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
        if (value === 'attachment') result.hasAttachment = true;
        break;
      case 'label':
        (result.label ??= []).push(value);
        break;
      case 'is':
        if (value === 'unread') result.isUnread = true;
        break;
    }
  }
  
  // Remaining text is body search
  if (remainingQuery) {
    result.body = remainingQuery.split(/\s+/).filter(Boolean);
  }
  
  return result;
}
```

### Pattern 2: Suggestion Generation from Parsed Query
**What:** Generate broader queries by systematically removing restrictive operators
**When to use:** When original query has operators that can be broadened
**Example:**
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

function generateBroaderSuggestions(
  parsed: ParsedQuery
): SearchSuggestions | null {
  const suggestions: SearchSuggestion[] = [];
  
  // Strategy 1: Extract names from from:/to:/subject: and search all fields
  if (parsed.from?.length) {
    for (const sender of parsed.from) {
      // Extract words from sender (e.g., "Don Stratton" -> ["Don", "Stratton"])
      const words = sender.split(/\s+/);
      for (const word of words) {
        if (word.length > 2) { // Skip very short words
          suggestions.push({
            query: word,
            reason: `Search all fields for "${word}" instead of just the sender`
          });
        }
      }
    }
  }
  
  // Strategy 2: Remove date restrictions
  if (parsed.after || parsed.before) {
    const withoutDates = buildQueryWithout(parsed, ['after', 'before']);
    if (withoutDates) {
      suggestions.push({
        query: withoutDates,
        reason: 'Remove date restrictions to search all time'
      });
    }
  }
  
  // Strategy 3: Remove label restrictions
  if (parsed.label?.length) {
    const withoutLabels = buildQueryWithout(parsed, ['label']);
    if (withoutLabels) {
      suggestions.push({
        query: withoutLabels,
        reason: 'Search all labels instead of specific ones'
      });
    }
  }
  
  // Only return suggestions if query had restrictive operators
  if (suggestions.length === 0) {
    return null; // Simple query, no suggestions needed
  }
  
  return {
    noResults: true,
    broaderQueries: suggestions.slice(0, 5), // Limit to 5 suggestions
    prompt: `No emails found matching "${parsed.raw}". Would you like me to try a broader search?`
  };
}
```

### Anti-Patterns to Avoid
- **Over-engineering with AST parsers:** Don't use PEG.js/nearley for simple keyword extraction
- **Generic query libraries without configuration:** `search-query-parser` requires explicit keyword lists; using without config misses Gmail operators
- **Parsing negation for suggestions:** Don't suggest queries based on negated terms (e.g., `-from:spam`)
- **Generating too many suggestions:** Limit to 5 most useful, ordered by likelihood of success

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| URL query string parsing | Custom parser | Built-in `URLSearchParams` | Standard API handles encoding |
| Date parsing | Custom regex | `Date.parse()` or `new Date()` | Handles various formats |
| Email validation | Complex regex | Let Gmail API validate | Gmail already validates on send |

**Key insight:** The Gmail query parsing IS something to hand-roll because:
1. Gmail's syntax is non-standard (not URL query strings)
2. Existing libraries don't fully support Gmail's operator set
3. The scope is bounded (~8 operators)
4. Zero dependencies is valuable for an MCP server

## Common Pitfalls

### Pitfall 1: Forgetting Quoted Values
**What goes wrong:** Parser fails to capture `from:"John Doe"` as a single value
**Why it happens:** Basic split on whitespace breaks quoted strings
**How to avoid:** Regex that handles both `operator:value` and `operator:"quoted value"`
**Warning signs:** Test with multi-word names returns incomplete results

### Pitfall 2: Case Sensitivity in Operators
**What goes wrong:** `FROM:` or `From:` not recognized
**Why it happens:** Gmail is case-insensitive for operators, parser assumes lowercase
**How to avoid:** Convert operator to lowercase before switch statement: `operator.toLowerCase()`
**Warning signs:** Some queries parsed incorrectly depending on user capitalization

### Pitfall 3: Generating Suggestions for Simple Queries
**What goes wrong:** Plain text query `meeting notes` generates suggestions
**Why it happens:** Code always tries to generate suggestions
**How to avoid:** Return `null` if parsed query has no operators (only body text)
**Warning signs:** BSS-04 test fails ("Simple queries do not generate suggestions")

### Pitfall 4: Not Handling Empty Operator Values
**What goes wrong:** `from:` without value causes parser error
**Why it happens:** Regex assumes value is always present
**How to avoid:** Make value capture group optional, skip operators with empty values
**Warning signs:** Malformed queries crash the parser

### Pitfall 5: Modifying Search Results Response Shape
**What goes wrong:** Breaking existing API consumers by changing response type
**Why it happens:** Adding `suggestions` field without making it optional
**How to avoid:** Make `suggestions?: SearchSuggestions` optional, only include when needed
**Warning signs:** TypeScript errors in existing code that uses `searchMessages`

## Code Examples

Verified patterns from research:

### Complete Gmail Query Parser
```typescript
// Source: Derived from Gmail official operators documentation
// https://support.google.com/mail/answer/7190

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

function parseGmailQuery(query: string): ParsedQuery {
  const result: ParsedQuery = { raw: query };
  
  // Regex explanation:
  // (\w+): - captures operator name (from, to, subject, etc.)
  // (?:"([^"]+)"|(\S+)) - captures either "quoted value" or unquoted-value
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
      // Additional operators can be added here
    }
  }
  
  // Extract remaining text (body search terms)
  // Sort ranges in reverse to remove from end first
  matchedRanges.sort((a, b) => b[0] - a[0]);
  let remaining = query;
  for (const [start, end] of matchedRanges) {
    remaining = remaining.slice(0, start) + remaining.slice(end);
  }
  remaining = remaining.trim();
  
  if (remaining) {
    // Handle quoted phrases in body text
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
```

### Suggestion Generator with Ranking
```typescript
// Source: Feature spec requirements

interface SearchSuggestion {
  query: string;
  reason: string;
}

interface SearchSuggestions {
  noResults: boolean;
  broaderQueries: SearchSuggestion[];
  prompt: string;
}

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
  
  // Strategy 1: Extract names/words from field-specific operators
  const fieldOperators: Array<{ field: string[]; name: string }> = [
    { field: parsed.from || [], name: 'sender' },
    { field: parsed.to || [], name: 'recipient' },
    { field: parsed.subject || [], name: 'subject' },
  ];
  
  for (const { field, name } of fieldOperators) {
    for (const value of field) {
      // Split multi-word values (e.g., "Don Stratton" -> ["Don", "Stratton"])
      const words = value.split(/\s+/).filter(w => w.length > 2);
      for (const word of words) {
        suggestions.push({
          query: word,
          reason: `Search all fields for "${word}" instead of just the ${name}`
        });
      }
      // Also suggest the full value without the operator
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
  
  // Deduplicate and limit suggestions
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
```

### Integration with searchMessages
```typescript
// Source: Feature spec - integration pattern

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
        ...result,
        suggestions,
      };
    }
  }

  return result;
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Generic query parsing libraries | Purpose-built parsers | Ongoing | Libraries like `search-query-parser` haven't been updated since 2021; hand-rolled solutions are preferred for specific domains |
| Complex AST-based parsing | Regex extraction for bounded operator sets | Always valid | For known, bounded operators, regex is simpler and faster |

**Deprecated/outdated:**
- `querystring` npm package: Use `URLSearchParams` instead (but neither applies here - Gmail uses custom syntax)

## Open Questions

Things that couldn't be fully resolved:

1. **Negation operator support (`-from:someone`)**
   - What we know: Gmail supports negation with `-` prefix
   - What's unclear: Should suggestions include negated terms or exclude them entirely?
   - Recommendation: Initially exclude negated operators from suggestion generation; add later if needed

2. **OR operator handling**
   - What we know: Gmail supports `from:a OR from:b`
   - What's unclear: How to generate broader suggestions for OR queries
   - Recommendation: Parse OR queries but don't generate suggestions for them (complex)

3. **Performance impact**
   - What we know: Parsing happens after zero results, minimal impact
   - What's unclear: Should we cache parsed queries?
   - Recommendation: No caching needed - queries are small strings, parsing is O(n) with small n

## Sources

### Primary (HIGH confidence)
- [Gmail Search Operators - Official Documentation](https://support.google.com/mail/answer/7190) - Complete operator list and syntax
- [Gmail API Filtering Documentation](https://developers.google.com/workspace/gmail/api/guides/filtering) - API-specific search behavior

### Secondary (MEDIUM confidence)
- [search-query-parser GitHub](https://github.com/nepsilon/search-query-parser) - Reference implementation patterns (v1.6.0, 2021)
- [Stack Overflow regex patterns](https://stackoverflow.com/questions/10598891/regex-for-gmail-like-search) - Community patterns for Gmail-like parsing

### Tertiary (LOW confidence)
- WebSearch results on TypeScript parsing patterns - General guidance only

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official Gmail docs + npm package analysis
- Architecture: HIGH - Clear requirements, bounded scope
- Pitfalls: HIGH - Derived from test cases and Gmail behavior

**Research date:** 2026-01-29
**Valid until:** 2026-03-01 (Gmail operators stable, unlikely to change)
