# GitHub publication scope and reproducibility

Base: `for-work` at `e620b2c5362a228d19b6cb91e8b7705c9823b347`. This branch preserves the existing branches and contains separate prerequisite commits for restoring the application frontend (archiving the showcase) and the persisted memory/ownership boundary that the personal map requires.

The imported working tree also contained unrelated web-search and model-tool changes. Those are deliberately **not** included. Mixed Python files were split by memory-specific hunks. The four map directions are implemented here as the documented rule-based MVP, not as full arbitrary-language semantic extraction.

No database dump, account token, transfer manifest, local credential file, dependency folder or local build output is published. Historical local backend credential defaults are replaced with `DB_PASSWORD`, `MINIO_ACCESS_KEY`, and `MINIO_SECRET_KEY`; supply these in the deployment environment. The frontend defaults to same-origin `/api`; its example configuration contains no machine address. Existing local credentials must not be overwritten by a snapshot.

## Revalidated on the actual publication tree

- Frontend: 384 passing tests, 2 existing integration skips; TypeScript check and production build pass. Existing large-bundle warning remains.
- Backend: 53 passing tests, excluding only the externally configured `LearningPlatformApplicationTests` context-load test.
- Browser against the production map controller and real H2 SQL services: evidence events, accept/reject persistence after reload, withdrawal/reconfirmation, and private source-context draft without automatic sending pass.
- Sources of the 37 map delivery files were checked against the tested candidate. Only required prerequisites were integrated from the imported worktree.

This is **not** production-login/Redis/MySQL/MinIO/LLM end-to-end acceptance. Test-only identity and SQL fixtures are confined to test source. See the v2 delivery report and `backend/LEARNING_MAP_TESTING.md` for boundaries and commands.

Python memory prerequisites were independently rechecked after splitting mixed search/memory changes: **72 tests passed** (`test_agent_memory.py`, `test_agent_memory_independent_acceptance.py`, `test_memory_statement_routing.py`). Two migration-redacted credential-shape test inputs were restored as clearly synthetic strings constructed inside tests; production filtering was not relaxed. These tests use mocked model paths and do not call a real LLM.
