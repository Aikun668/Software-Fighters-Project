# Learning map frontend verification

- `pnpm install --frozen-lockfile`: success; original lockfile unchanged.
- `vitest run`: 26 passed files, 1 skipped; 375 passed tests, 2 skipped (existing integration tests), 2026-11-10 cloud validation.
- `vue-tsc --build`: success.
- `vite build`: success; existing >500 kB bundle warnings remain.
- Initial new map tests failed against old hard-coded demo; implemented map passes empty state, local graph, isolated node, source navigation, draft navigation, failure/retry, unavailable privacy-state handling. Chat handoff tests cover draft/no-send and saved-message anchor.
- Browser: Chromium Headless Shell 134 + Playwright 1.51.1, desktop 1440x1000 and mobile 390x844. Cloud socket restrictions prevented Vite listening. Browser route interception served real `dist` assets; API responses were explicit fixtures, not real DB. Passed render, selected-node evidence, one-hop filter, draft handoff without sending, mobile rendering. Screenshots are UI contract evidence only, not live authenticated end-to-end evidence.
- Screenshot review found tiny mobile nodes: fixed with a 700px scrollable minimum canvas, regenerated screenshots. Large graph layout uses a nonoverlapping grid, reflowed per local/search filter; force-directed simulation intentionally deferred.
- Fixed two existing dependency API/type mismatches discovered during build: Axios interceptor unwrapped result needs explicit Promise<T> assertion; Mermaid render returns `bindFunctions` (plural).

Screenshots: `desktop-fixture.png`, `chat-draft-fixture.png`, `mobile-fixture.png`. The companion script records the reproducible scenario; adjust filesystem/browser paths for another environment. No fixtures are shipped in application data or fallbacks.

To rerun UI checks: install `playwright@1.51.1` in a separate tooling directory, install its Chromium browser, build frontend, then run the script with that directory on `NODE_PATH`. Optionally set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to an existing browser executable. Repository and output paths resolve from the script location; no source edits needed. Example on Linux:

```sh
NODE_PATH=/path/to/tooling/node_modules PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/headless_shell node docs/verification/learning-map/ui-fixture-check.cjs
```

The test deliberately intercepts browser network responses and creates no user accounts or DB records.

## Phase 2: trajectory, suggestions, continuation

- Full Vitest: **381 passed, 2 skipped**, 26 passed files and 1 skipped integration file.
- `vue-tsc --build` and `vite build`: pass; existing bundle-size advisory remains.
- Added real event types (goal/question/practice request/self-report), evidence navigation, persistent accept/reject and reversal controls, separate dashed `user_confirmed` edges, server-verified context continuation. Practice self-reports are explicitly unverified; no completion score is synthesized.
- Tests cover busy locks, failed decision retry, rejection and confirmation state, reversal, unavailable data, source navigation, stale continuation after selecting another node, draft/no-send.
- `ui-real-api-check.cjs` calls a long-lived **real Java MockMvc controller + H2 + production memory/decision services** process for every learning-map request. It passes evidence events, accept/reject persistence after browser reload, user-confirmed edges, withdrawal/reconfirmation and current-source continuation. This is not static map API mocking. Test identity and seeded conversations are isolated integration fixtures, not production login or user data. Other sidebar endpoints are stubbed empty because they are outside this map acceptance scope.
- Actual browser screenshots: `trajectory-real-api.png`, `suggestions-real-api.png`, `continuation-real-api.png`.
- Start the backend test bridge `com.university.learning.graph.LearningMapBrowserBridge` with compiled test + main classes and dependency classpath; put its launcher in `LEARNING_MAP_BRIDGE_COMMAND`, then run the real API script with the same `NODE_PATH` and optional `PLAYWRIGHT_CHROMIUM_EXECUTABLE` as above. The bridge communicates on stdin/stdout to avoid cloud network-listener restrictions. No production account or data is needed for this isolated test.

## Privacy review correction

Source-containing continuation drafts now cross views via a one-use **memory-only** handoff keyed by a random opaque handle. No source excerpt is written to the URL, localStorage, or sessionStorage. Only `learningContext=<opaque handle>` appears in navigation. Wrong/stale handles cannot consume the draft; successful consumption clears it; page reload loses it rather than replaying private context. Existing generic `draft` URL inputs remain compatible, but the learning-map flow never uses them.

Post-correction full suite: **383 passed, 2 skipped** (27 passed files / 1 skipped); typecheck and build pass. Real API browser validation additionally asserts no `draft` query parameter in continuation navigation and checks that the private context still reaches the input without sending.

HTTP LAN gateway compatibility: opaque handles prefer `crypto.randomUUID`; when unavailable, use 16 cryptographically random bytes from `crypto.getRandomValues` encoded as hex. No `Math.random` fallback. Added missing-`randomUUID` regression test. Latest full suite **384 passed, 2 skipped**; typecheck and production build pass.
