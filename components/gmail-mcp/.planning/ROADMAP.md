# Roadmap: @technetcentral/gmail-mcp-server

**Created:** 2026-01-27
**Milestone:** v1.0 — Deployment Ready

## Overview

| Phase | Name | Goal | Status |
|-------|------|------|--------|
| 1 | Package Configuration | Update package.json metadata | ✓ Complete |
| 2 | Dependencies | Add open package for browser auto-launch | ✓ Complete |
| 3 | Build | Compile TypeScript to JavaScript | ✓ Complete |
| 4 | Git Setup | Initialize repo with proper .gitignore | ✓ Complete |
| 5 | MCP Client Config | Configure Gmail servers in n8n_builder | ✓ Complete |
| 6 | Debug & Verify | Fix token refresh issues, verify working | In Progress |
| 7 | Broader Search Suggestions | Suggest broader queries when search returns no results | Pending |

---

## Phase 1: Package Configuration ✓

**Goal:** Update package.json with correct metadata for npm publishing

**Requirements:** PKG-01, PKG-02, PKG-03

**Status:** Complete

---

## Phase 2: Dependencies ✓

**Goal:** Add open package for browser auto-launch during auth

**Requirements:** DEP-01

**Status:** Complete

---

## Phase 3: Build ✓

**Goal:** Compile TypeScript without errors

**Requirements:** BLD-01, BLD-02

**Status:** Complete

---

## Phase 4: Git Setup ✓

**Goal:** Initialize git repo with proper configuration

**Requirements:** GIT-01, GIT-02, GIT-03

**Status:** Complete

---

## Phase 5: MCP Client Config ✓

**Goal:** Configure Gmail MCP servers in n8n_builder workspace

**Requirements:** MCP-01, MCP-02, MCP-03

**Status:** Complete

---

## Phase 6: Debug & Verify

**Goal:** Debug why Gmail MCP server isn't working, verify token refresh

**Requirements:** VER-01, VER-02

**Plans:** 1 plan

Plans:
- [ ] 06-01-PLAN.md — Diagnose server loading, verify with user, fix issues

**Success Criteria:**
1. Gmail tools appear in MCP client after restart
2. `list_messages` returns recent emails without auth errors
3. Token refresh works transparently when token is expired

**Status:** In Progress

---

## Phase 7: Broader Search Suggestions

**Goal:** When Gmail search returns zero results, suggest broader search queries

**Requirements:** BSS-01, BSS-02, BSS-03, BSS-04

**Feature Spec:** .planning/features/BROADER_SEARCH_SUGGESTIONS.md

**Plans:** 1 plan

Plans:
- [ ] 07-01-PLAN.md — Add query parser, suggestion generator, integrate with searchMessages

**Success Criteria:**
1. Zero-result searches with restrictive operators return suggestions
2. Suggestions include broader query and human-readable reason
3. Simple queries (no operators) do not generate suggestions
4. Query parser handles quoted strings and all common Gmail operators

**Status:** Planned

---

## Milestone Summary

**v1.0 — Deployment Ready**
- 7 phases
- Phases 1-5: Complete
- Phase 6: In Progress (debugging)
- Phase 7: Pending (broader search suggestions)

---
*Roadmap updated: 2026-01-29*
