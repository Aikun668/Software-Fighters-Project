# Independent adaptive-plan MVP review

Reviewed against `docs/superpowers/plans/2026-11-10-adaptive-plan-mvp.md` and baseline `741292e`.

## Findings addressed during review
- P1: Future empty modules could not be refined, breaking the rolling-plan loop. Added versioned module task creation and frontend refinement controls.
- P1: Deferred tasks disappeared from the actionable queue without a restoration control. Added explicit re-inclusion while retaining checkpoint and completed work.
- P2: Split change previews included preceding unrelated tasks. Preview now contains only the parts of that source task.
- P2: Deadline conflict resolutions changed additional tasks without enumerating them before confirmation. Preview now includes exact deferred task list and extended deadline.
- P2: Proposal-time date could become stale. Apply rejects proposals from another date and recomputes current capacity.
- P2: Negated instructions could trigger the opposite change; recognized same-value budgets were rejected. Conservative rejection and recognition corrected.
- P2: Empty future modules incorrectly allowed overall plan completion. Plan remains open until modules have defined completed work; task completion remains self-reported.
- P2: Impossible initial deadlines had no visible warning. Persistent capacity warnings now surface on reads and creation.
- P2: Frontend deadline-resolution values and input limits disagreed with backend contract. Aligned and tested.
- P2: Raw JSON previews and generic Axios messages obscured actual decisions/errors. Human-readable task summaries and backend error messages now displayed.
- P2: In-flight initial list reads could overwrite a newly created plan. Loading and sequence guards added.

## Independently executed checks
- `AdaptivePlanIndependentReviewTest`: **4 passed** with real H2 SQL, including simultaneous same-version writers (exactly one succeeds, one gets 409), all write routes' owner isolation, future-module refinement without losing completed work, and date-expired proposal rejection.
- `AdaptivePlanWorkspace.spec.ts`: **16 passed** on the reviewed frontend.

The reviewer added only a separate regression test class and this report, not production implementation. Ordinary agent tests, full regressions and browser evidence are recorded separately by the implementers and acceptance worker.

## Boundaries
The visible plan workspace is a deterministic, limited-language MVP. General chat/research prose is not a tool that silently mutates this durable plan. Continuation drafts are user-reviewed before sending. The SQL/CAS checks do not constitute production MySQL, Redis authentication or real LLM acceptance. Unrelated legacy plan endpoints remain a separate system and are not certified by this review.

## Final chat handoff check
- Fixed an additional P2 interruption boundary: a continuation request arriving during streaming is consumed after the response, not silently ignored; an existing unsent prompt is preserved instead of overwritten. Consumed tokens cannot later clear the prompt.
- Conversation URL synchronization preserves the selected adaptive plan and opaque one-use context token, not private context text.
- Independently rerun `QuestionNavChat.spec.ts`: **44 passed** after correcting the test stream to invoke its real completion callback. No unresolved blocking findings in the reviewed MVP scope.
