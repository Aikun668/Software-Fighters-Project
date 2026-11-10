# Adaptive plan backend MVP

## Storage and deployment

- `AdaptivePlanService` uses the configured Spring `JdbcTemplate` datasource. Production is MySQL; tests use H2 MySQL compatibility mode.
- On first use it creates `adaptive_plan` (owner, version, JSON state, single undo snapshot) and `adaptive_plan_proposal` (owner, plan, immutable JSON preview). The app DB account requires CREATE TABLE, SELECT, INSERT and UPDATE on those tables. No existing plan/chat tables are rewritten.
- Each mutation is one atomic `UPDATE ... WHERE user_id=? AND id=? AND version=?`; conflict returns HTTP 409. Proposals persist a preview but never change current plan/version. Failed confirmation does not apply partial edits.
- Every API uses the authenticated `UserHolder`; no client user ID is trusted. Production auth configuration remains a deployment responsibility.
- New feature deliberately has a separate durable store from the legacy generated-plan system. It does not import historical static UI tasks or infer mastery.
- Proposal engine is explicit bounded rules, not an LLM. Unsupported or negated adjustments fail safely. It recognizes daily minutes, checkpoint/blocker and defer requests. Optional `taskId` limits adjustment; otherwise only the next three unfinished tasks are refined.
- A changed plan version or changed date invalidates a proposal. Deadline conflict choices preview exact extension date or deferred task list before confirmation.
- Undo only applies immediately after an adjustment. Any saved progress, new task or subsequent undo clears the undo snapshot so newer progress is never overwritten.
- Empty future modules can be refined through `POST /api/adaptive-plans/{id}/modules/{moduleId}/tasks`. Deferred tasks resume via status `pending`.

## API

All responses use the existing `{code,message,data}` envelope. Validation uses HTTP 400; missing/other-user resources 404; stale versions 409; missing user 401.

- `GET/POST /api/adaptive-plans`: list/create.
- `GET /api/adaptive-plans/{id}`: current plan with nextTasks (maximum three), canUndo and capacityWarning.
- `PATCH /api/adaptive-plans/{id}/tasks/{taskId}`: version + status/checkpoint/nextAction.
- `POST /api/adaptive-plans/{id}/modules/{moduleId}/tasks`: version + title/minutes/nextAction.
- `POST /api/adaptive-plans/{id}/proposals`: version + message, optional taskId/dailyMinutes/deadline.
- `POST /api/adaptive-plans/{id}/proposals/{proposalId}/apply`: version, resolution `extend` or `defer` when needed.
- `POST /api/adaptive-plans/{id}/undo`: version.

## Targeted verification

From repository root (normal Maven/JDK 17 environment):

```sh
mvn -f backend/pom.xml -Dtest=AdaptivePlanServiceTest test
```

Cloud toolchain equivalent:

```sh
JAVA_HOME=/workspace/shared/tooling/jdk-17.0.21+9 \
/workspace/shared/tooling/apache-maven-3.9.9/bin/mvn \
-s /workspace/shared/tooling/settings.xml \
-Dmaven.repo.local=/workspace/shared/tooling/m2 \
-f backend/pom.xml -Dtest=AdaptivePlanServiceTest test
```

14 focused tests: ownership/reopen persistence, proposal isolation, effort conservation, completed/checkpoint preservation, pause/resume, stale progress, undo protection, explicit deadline choice and both resolutions, malformed/overflow inputs, unsupported/negated intent, future module refinement, exact preview/date invalidation. Real MySQL persistence across process restart and production authentication/LLM are not validated by these H2 tests.
