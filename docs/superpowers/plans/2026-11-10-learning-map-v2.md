# Learning map completion: trajectory, proposals and contextual continuation

**Authorized scope:** User approved completing items 2, 3 and 4 and integrated testing before publication.

**Architecture:** Extend the authenticated map projection, keeping raw evidence subject to existing forgetting/privacy boundaries. Trace goals/questions/practice requests/self-reports separately from knowledge concepts. Offer transparent cross-domain candidate links; store each user's accept/reject decision, never label acceptance as a proven dependency. Continue learning with server-revalidated quoted sources in a user-reviewed draft.

## Tasks and gates
- [x] Backend: add source-backed events and small-rule-domain proposals with bounded output; verify identity, missing/deleted/forgotten evidence and false completion claims.
- [x] Backend: persist per-user proposal decisions through Jdbc, revalidate current candidate on each write, expose non-factual user_confirmed links; test retries/isolation/reject transitions.
- [x] Backend: node continuation endpoint rebuilds readable graph and returns bounded draft with quoted evidence, explicit context boundaries and source identifiers. Missing nodes return not-found.
- [x] Frontend: quiet Map / Trajectory / Suggestions tabs; explicit request vs self-report and pending vs user-confirmed; no implied mastery/completion.
- [x] Frontend: lock duplicate writes, retain retryable error state, prevent stale continuation navigation, draft never auto-sends.
- [x] Integration: real H2 persistence + real Java controllers via MockMvc; browser uses real built frontend and bridge to test application if socket listening unavailable. Fixtures seed test DB only, not fake successful API responses. Distinguish this from production login/model verification.
- [x] Independent review, regression suites, screenshots, portable verification scripts and change log. No Git push from implementation worker.

**Contract:** GET /api/learning-map adds events and suggestions; POST /api/learning-map/suggestions/{id}/decision accepts accepted|rejected; GET /api/learning-map/nodes/{id}/continuation returns {draft}. Existing nodes/edges/meta remain compatible.

**Remaining external gate:** User's real database, sign-in and model configuration are not part of transferred source. Do not fabricate credentials or report that environment as tested.

Completion scope: isolated integrated chain verified; deployment-specific external gate remains explicitly pending. No implementation-worker push performed.
