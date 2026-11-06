# Phase 7 Context: Broader Search Suggestions

## Phase Goal

When Gmail search returns zero results, suggest broader search queries that might help the user find what they're looking for.

## Problem Being Solved

A user searched for `from:Don Stratton` but got no results. The email existed but was sent from `crownking62@yahoo.com` with "Don Stratton" mentioned only in the email body. The manual intervention (suggesting `Stratton` as a broader search) should be automated.

## Key Requirements

- **BSS-01**: Query parser correctly parses Gmail search operators
- **BSS-02**: Query parser handles quoted strings
- **BSS-03**: Suggestion generator returns broader queries for restrictive operators
- **BSS-04**: Simple queries do not generate suggestions

## Technical Context

### Codebase Structure
- Main source file: `src/tools.ts`
- This is an MCP (Model Context Protocol) server for Gmail
- Built with TypeScript

### Modification Points
The feature spec identifies `src/tools.ts` as the primary file to modify.

### Key Components Needed
1. **Query Parser** - Parse Gmail search queries into structured components
2. **Suggestion Generator** - Generate broader search suggestions based on parsed query
3. **Response Enhancement** - Add `suggestions` field to search responses when appropriate

## Feature Specification

Full specification: `.planning/features/BROADER_SEARCH_SUGGESTIONS.md`

## Prior Decisions

None specific to this phase yet.
