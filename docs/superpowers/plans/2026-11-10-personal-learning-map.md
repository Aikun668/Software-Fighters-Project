# Personal Learning Map Implementation Plan

> **For agentic workers:** Execute task-by-task with independent backend/frontend workers and integration review.

**Goal:** Replace the static graph with an evidence-backed personal learning map, source navigation, and continued conversation.

**Architecture:** The authenticated Java gateway projects the user's persisted conversation evidence into nodes and explicitly supported edges. Vue renders that projection, never course skeletons or invented mastery. The projection remains separate from the existing memory key/value slots.

**Tech Stack:** Java 17 / Spring Boot / MyBatis, Vue 3 / TypeScript / SVG / Vitest.

**Spec:** User's approved map request: extract learning nodes from conversations/memory; connect only genuine relationships; retain isolated points; trace sources; continue learning from a node. Force physics is secondary.

## Global Constraints
- Preserve all imported uncommitted work and the restored root frontend.
- No fabricated mastery percentages, nodes, relation counts, credentials or user data.
- User identity comes from authenticated gateway context, not a client userId.
- No new public deployment, paid service or schema migration needed for this MVP.
- Cloud snapshot cannot prove production DB or model integration without configuration.

## Review Focus
- Another user's conversations must never appear in the graph.
- Negation and relationship questions must not become asserted edges.
- Empty data and failed APIs must not silently display sample data.
- Continued conversation must prefill a draft, not silently send on user's behalf.
- Deleted evidence and repeated visits must not create stale or duplicate nodes.

## Task 1: Evidence projection and gateway
- [x] Inspect persisted conversations, ownership and memory suppression.
- [x] Write extraction tests for explicit learning topics, isolated nodes, evidenced relationships, negation/questions, deduplication and bounds.
- [x] Add GET /api/learning-map returning nodes (id,title,summary,sources,firstSeen,lastSeen), edges (id,source,target,relation,evidence), and extraction metadata.
- [x] Run backend tests, record any dependency/configuration blockers accurately.

## Task 2: Map and conversation navigation
- [x] Replace hardcoded KnowledgeGraphPage with typed endpoint and loading/error/empty states.
- [x] Implement global/local view, search, isolated points, zoom and evidence detail.
- [x] Add source-conversation navigation and prefilled continuation draft.
- [x] Test map rendering and source/continuation flows; type-check and production-build.

## Task 3: Independent review and delivery
- [x] Review gateway ownership, limits and evidence semantics independently.
- [x] Run integrated UI/API contract tests; screenshot representative states if browser available.
- [x] Document changed files, quantitative results, launch procedure and precise limitations.
- [x] Package changes separately from the user's untouched local original.

Execution note: Cloud implementation and automated/fixture UI checks complete; actual account/database end-to-end remains a user-environment acceptance gate, not a passed check.
