# Assesify — Test / Spec Compliance Status

Last updated: 2026-08-24. Reflects actual current state after manual tracing,
running the backend pytest suite, and targeted end-to-end smoke calls against
an in-memory SQLite Flask test client. Not a plan — a snapshot.

Markers: `[x]` implemented & verified · `[ ]` missing · `[~]` partial · `[B]` blocked by external creds/services (fallback path verified).

## Data Model (spec §3)
- [x] `users` — `backend/app/models/users.py` (role via `is_teacher`, `karmayogi_user_id`, Argon2 hash)
- [x] `materials` — `backend/app/models/assessment.py::Material`
- [x] `quizzes`/`questions` — **unified this session**: all quiz-generation write paths (`POST /teacher/materials`, `POST /lessons/:id/quiz`, `POST /materials/:id/generate-quiz`) now persist relational `app/models/assessment.py::Question` rows (via a new shared `app/services/quiz_generation.py::persist_quiz_questions()` helper) instead of the JSON blob. There was only ever one `Quiz` table (`app/models/quiz.py::Quiz`, `quizzes`) — the "two schemas" were really one `Quiz` row plus two different ways of storing its questions (JSON blob column vs. relational `Question` rows keyed by `quiz_id`); `Quiz.questions` is kept (not dropped, see caveat below) but no code writes to it any more. `Quiz.to_dict()` now derives its legacy `questions` JSON shape from relational `Question` rows when they exist (via `quiz_generation.legacy_shape_from_questions()`), falling back to the raw blob only for quizzes created before this change — so the frontend quiz-taking page (`GET /api/quizzes/:id`, consumed by `frontend/app/quiz/[id]/page.tsx`) needed zero changes. `PersonalizedQuizService` (ad-hoc personalized/weekly-test quiz generation) was the last remaining JSON-blob writer and has now also been converted — see the 2026-08-26 follow-up entry at the bottom. **No code writes `Quiz.questions` any more.**
- [x] `attempts`/`responses` — `app/models/submission.py::QuizAttempt`, `QuizAnswer`
- [x] `competency_mastery` — `app/models/mastery.py`
- [x] `recommendations` table — **persisted this session**: `GET /students/:id/recommendations` (`backend/app/api/v1/students/routes.py`) now upserts each computed recommendation into `Recommendation` (`app/models/mastery.py`) keyed on `(student_id, competency_tag, karmayogi_course_id)`, storing score/reason/title/url/created_at. Computation path (`karmayogi_service.recommend_for_gap`) unchanged. Verified live via a smoke script: one gap → one DB row confirmed (`DB rows: [(1, 'budgeting', None, 1.0)]`); backend pytest suite still `26 passed`.
- [x] `refresh_tokens` — `app/models/refresh_token.py` + migration (per recent commit)
- [x] Actual Postgres deployment — **verified 2026-08-26** against a real Dockerized PostgreSQL 16 on port 5433 (see the final follow-up entry): all 18 migrations reach head `a1b2c3d4e5f7`, and a scripted HTTP flow (register/login/quiz/attempt/submit/result) passes 10/10 against Postgres. One real PG-only migration bug (boolean `server_default`) was found and fixed. Originally recorded as: dev/test run on SQLite — dev/test run on SQLite (`backend/assesify_dev.db`, `sqlite:///:memory:` in tests); no Docker Postgres available in this environment. Models are dialect-agnostic SQLAlchemy so Postgres should work, but untested here.
- [x] Alembic migration heads — **fixed this session**: `backend/migrations/versions/` had **three** divergent unmerged heads (`76d4ba2e9c10`, `840eb69db66d`, `e5f6a7b8c9d0`, all descending from `f5c8d1966aa6`), not the two previously guessed. Traced the full `down_revision` chain manually (confirmed via `flask db heads` once invoked correctly — the trick is `FLASK_APP=app.main:app`, since `app/main.py` builds a top-level `app = create_app()` instance rather than a factory function alembic can call by name). Reconciled with `flask db merge -m "merge divergent heads" 76d4ba2e9c10 840eb69db66d e5f6a7b8c9d0`, producing `migrations/versions/c34d7f13f504_merge_divergent_heads.py` (single new head, no-op up/down). While verifying `flask db upgrade head` against a scratch SQLite DB (`backend/scratch_migration_test.db`, deleted after, `assesify_dev.db` never touched), found and fixed a **second real bug**: `840eb69db66d_add_profile_pic_to_user_and_teacher_id_.py` called `batch_op.create_foreign_key(None, ...)` / `batch_op.drop_constraint(None, ...)` — SQLite's batch-mode ALTER TABLE emulation requires a named constraint, so upgrade raised `ValueError: Constraint must have a name` and would have failed for anyone actually running migrations against SQLite. Fixed by naming the constraint (`fk_lessons_teacher_id_users`) in both `upgrade()` and `downgrade()`. Verified: `flask db upgrade head` now runs cleanly end-to-end against a fresh scratch DB (13 migrations in order, ending at `c34d7f13f504`). Full pytest suite re-run after: `32 passed, 0 failed` — no regressions.

## Auth API (spec §4.1)
- [x] `POST /auth/register`, `POST /auth/login` (Argon2 password hashing, verified via `backend/app/tests/test_security_helpers.py`)
- [x] `POST /auth/refresh` — refresh_tokens table + rotation present
- [x] `POST /auth/karmayogi/link` — bare ID linking, retained for administrative/known-id linking.
- [x] **OAuth2 client-credentials + authorization-code/PKCE — implemented this session** (spec §6.1). `ml/integrations/karmayogi/oauth.py` rewritten: added `derive_code_challenge`/`verify_code_challenge` (S256, constant-time compare), `generate_state`, a single `_post_form()` HTTP seam (the one place tests mock), RFC-6749-§5.2 error handling (`OAuthError`/`OAuthConfigurationError`, including JSON error bodies on HTTP 400), `fetch_userinfo()`, `extract_user_id()` (tries `karmayogi_user_id`/`sub`/`userId`/`user_id`/`identifier`/`id` across the token and userinfo payloads), and `get_service_token()` — an in-process client-credentials token cache with a 30s expiry skew, plus `reset_service_token_cache()`. New `app/models/oauth_state.py::OAuthState` (+ migration `f6a7b8c9d0e1_add_oauth_states.py`) stores the `state` → (user_id, code_verifier, redirect_uri, expiry, consumed) binding server-side; the verifier never leaves the backend. New `app/services/karmayogi_oauth_service.py` implements `begin_authorization()`/`complete_authorization()`; two new routes `POST /auth/karmayogi/authorize` and `POST /auth/karmayogi/callback` (both `@jwt_required`) in `app/api/v1/auth/routes.py`, plus their OpenAPI definitions in `backend/openapi.yaml` (types regenerated). `app/services/karmayogi_service.py::recommend_for_gap` now attaches a client-credentials `Bearer` token to catalog calls when `KARMAYOGI_TOKEN_URL` is configured, falling back to the previous HTTP Basic header otherwise.
  - Security properties enforced and tested: single-use state (burned *before* the network call, so a concurrent replay can't reuse the verifier), ownership check (another user's state is rejected), expiry check, unknown/forged state rejected **without any token exchange being attempted**, and 503 rather than a pretend-success when Karmayogi OAuth is unconfigured.
  - New `backend/app/tests/test_karmayogi_oauth.py` — 18 tests, all passing, all HTTP mocked at `_post_form`/`fetch_userinfo`: challenge derivation/verification, authorize-URL contents (`code_challenge_method=S256`, state echo, challenge matches the stored verifier), token exchange carrying the right verifier, userinfo fallback to token claims, CSRF/forged-state rejection, cross-user state rejection, replay rejection, expiry rejection, provider `invalid_grant` surfaced as 502 with details, unresolved-identity handling, missing-code/state validation, client-credentials grant body, service-token caching + forced refresh + not-caching-already-expired-tokens, and graceful `None` when the token endpoint is unreachable or unconfigured.
- [x] Rate limiting on auth endpoints — custom in-memory sliding-window limiter (`app/core/rate_limit.py::ratelimit_for_auth`, 60/min) applied to login & register (not Flask-Limiter as spec literally names, but equivalent behavior). Single-process only (not distributed) — fine for v1.

## Materials & Generation API (spec §4.2)
- [x] `POST /materials` — `app/api/v1/materials/routes.py`, teacher-only, MIME+size validation via `app/core/uploads.py` (25MB cap, magic-byte sniffing for pdf/docx, UTF-8 check for txt). Verified via `backend/ml/tests/test_upload_endpoint.py` (rewritten this session, passes).
- [x] `GET /materials/:id`
- [x] `POST /materials/:id/generate-quiz` — routes to `ml/train/quiz_gen.py`
- [~] Legacy duplicate: `POST /teacher/materials` (`app/api/v1/teacher/routes.py`) still does upload+extract+generate+persist synchronously in one call (vs. the two-step `/materials` + `/materials/:id/generate-quiz` flow) — that duplication of *endpoints* remains. **Fixed this session**: it now writes the same relational `Question` rows as the primary flow (see Data Model section above), so the two endpoints are no longer architecturally divergent in how they store data, only in call shape (one-shot vs. two-step).
- [B] Gemini-based generation (`ml/gemini.py`, `ml/gemini_prompt.py`) — no `GEMINI_API_KEY` available in this environment. Rule-based fallback generator (`ml/train/quiz_gen.py::generate_quiz`) is what actually runs in tests/smoke calls and works correctly. Retry/fallback contract (spec §5.1 point 5) traced in code but not live-tested against real Gemini.

## Quizzes & Attempts API (spec §4.3)
- [x] `GET /quizzes`, `GET /quizzes/:id`
- [x] `POST /quizzes/:id/attempts`, `POST /attempts/:id/responses`, `POST /attempts/:id/submit`, `GET /attempts/:id/result`
- [x] Verified via `backend/app/tests/test_attempts.py::test_attempt_lifecycle` (passes) and a fresh manual smoke test (start attempt → answer → submit → score) run this session — 201/200/200 with correct scoring.

## Analytics & Recommendations API (spec §4.4)
- [x] `GET /students/:id/mastery` — `app/api/v1/students/routes.py`, backed by `mastery_service.refresh_student_mastery` (IRT-style logistic estimator, `app/services/irt.py`). Verified live: after one wrong response, mastery computed as 0.445 (sane, `< 0.6` threshold logic correct).
- [x] `GET /students/:id/gaps` — verified live: correctly flags `budgeting` gap with `gap_score = (0.6-mastery)`.
- [x] `GET /students/:id/recommendations` — verified live end-to-end; when Karmayogi is unreachable (no `KARMAYOGI_BASE_URL`), correctly falls back to internal remedial quiz recommendation with `source: "internal"`, `karmayogi_available: false`, and a clear `reason` string. This is the §6.4 fallback contract and it works.
- [x] `GET /teachers/cohorts/:id/analytics` — route registered at `/api/v1/teachers/cohorts/<int:class_id>/analytics` (in `classes` blueprint); ownership/role check present. Not run against live data this session (would need a seeded class+cohort) but code path traced and matches spec shape.
- [~] Legacy `GET /teacher/analytics` (no cohort id, all-lessons-for-teacher) also exists in `app/api/v1/teacher/routes.py` — redundant with the spec'd cohort endpoint but not harmful.

## ML Module (spec §5)
- [x] `mastery_service.py` + `irt.py` — logistic-regression-style mastery estimate, L2-ish regularization, 90-day response window (`cutoff = utcnow() - 90d`). Verified via `backend/app/tests/test_mastery_estimator.py` (passes) and live smoke test.
- [x] `ml/adaptive.py::select_next_question` — maximizes IRT information (p·(1-p)) near current competency mastery; simple, deterministic, matches spec §5.4 intent. Read and traced; no dedicated unit test existed, logic verified by manual read (correct math: peaks at mastery==difficulty).
- [x] **Fixed this session**: `ml/recommender.py::advanced_aggregate` had a real bug — `df.groupby([...,"subtopic"])` used pandas' default `dropna=True`, so when `subtopic` is `None` (the common case) every row was silently dropped, producing an empty output DataFrame and a `KeyError: 'avg_time_mean'` downstream. Fixed by passing `dropna=False` and hardening the empty-output branch. `backend/ml/tests/test_recommender.py::test_recommender_flow` now passes (was failing before).
- [~] Gemini quiz-generation JSON-schema validation + embedding-dedup (spec §5.1 step 5) — `ml/gemini.py`/`ml/gemini_prompt.py`/`ml/schemas.py` exist and are exercised by `ml/tests/test_gemini_prompt.py` / `test_gemini_integration.py` (pass, using mocks). Real Gemini call untested — see [B] above.
- [x] `ml/topic_models.py`, `ml/pipeline.py`, `ml/tasks.py` covered by their own passing tests (`ml/tests/test_topic_models.py`, `test_pipeline.py`, `test_tasks.py`, `test_quiz_gen.py`).

## Karmayogi Integration (spec §6)
- [x] Connector module layout matches spec exactly: `ml/integrations/karmayogi/{client.py,mapping.py,recommender.py,sync.py,oauth.py,taxonomy.py}`.
- [x] `client.py::KarmayogiClient` — retry w/ backoff, circuit-breaker-style cooldown (`_unavailable_until`), returns `[]` gracefully (never raises) from `list_courses` when unconfigured/unreachable.
- [x] **§6.4 fallback verified live**: `app/services/karmayogi_service.py::recommend_for_gap` — when `KARMAYOGI_BASE_URL` is unset (this environment), falls straight to `_internal_fallback()`, returning an internal remedial-quiz recommendation with an explicit `"Karmayogi is unavailable..."` reason string. Confirmed via direct smoke-test call this session.
- [x] Frontend banner — **added this session**: `frontend/components/MasteryRecommendations.tsx` now renders a visible "Karmayogi course catalog is unavailable..." banner when any recommendation has `karmayogi_available === false` (previously the fallback reason was only shown inline per-card, no dedicated banner per spec §6.4).
- [x] OAuth2 flow logic (client-credentials + PKCE authorization-code) — implemented and unit-tested this session with mocked token endpoints; see the Auth API section above for full detail.
- [B] **Live** handshake against a real Karmayogi sandbox (OAuth2 token/authorize/userinfo endpoints, course catalog, progress-push via `sync.py`) — no sandbox credentials exist in this environment, so only the live round-trip is unverified. Everything reachable locally was verified: the full PKCE state machine, token-exchange request shape, error/fallback paths, and the unconfigured-deployment path (503 rather than a fake success). `ml/integrations/karmayogi/tests/test_karmayogi_integration.py` still passes on the no-network paths.
- [~] Competency framework caching (24h TTL per §6.4 `KARMAYOGI_COMPETENCY_CACHE_TTL`) — `taxonomy.py` exists; did not verify actual cache-eviction timing behavior.

## Frontend (spec §7)
- [x] `/login`, `/register` — `frontend/app/(auth)/login|register/page.tsx`
- [x] `/dashboard` — `frontend/app/dashboard/page.tsx`; renders `MasteryRecommendations` (mastery bars + recs) for students, weekly-test panel, classes, pending quizzes.
- [x] Mastery visualization — **converted this session**: `frontend/components/MasteryRecommendations.tsx` now renders a Recharts `RadarChart` (`Radar`/`PolarGrid`/`PolarAngleAxis`/`PolarRadiusAxis`/`Tooltip`) plotting `competency_tag` vs mastery %, styled with the existing brand-blue token. `recharts` added to `frontend/package.json`. Verified via `npm run build` (Next.js/Turbopack) — compiles and generates static pages successfully.
- [x] `/quiz/[id]` — `frontend/app/quiz/[id]/page.tsx`
- [x] `/results/[attemptId]` — `frontend/app/results/[attemptId]/page.tsx`
- [x] `/teacher`, `/teacher/materials/[id]`, `/teacher/quizzes/[id]/analytics` — all present under `frontend/app/teacher/`.
- [x] API base URL — **fixed this session**: `frontend/lib/api.ts` now exports `API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:5000"` (127.0.0.1:5000 kept only as the local-dev default), and all previously-hardcoded call sites (`MasteryRecommendations.tsx`, `app/results/[attemptId]/page.tsx`, `app/quiz/[id]/page.tsx`, `app/teacher/materials/[id]/page.tsx`) now import and use it. Verified via grep — no remaining hardcoded `127.0.0.1:5000`/`localhost:5000` outside the single fallback default in `lib/api.ts`.
- [x] Shared OpenAPI-generated TS types (spec §7.3, `openapi-typescript`) — **implemented this session**: hand-authored `backend/openapi.yaml` (no OpenAPI extension existed in the backend — grepped for `flask-smorest`/`flasgger`/`apispec`/`flask-restx`/`openapi`/`swagger` across `backend/`, none found) describing the current API surface (auth, materials, quizzes, attempts, students/mastery/gaps/recommendations, classes, teacher/admin) based on reading the actual route handlers and model `to_dict()` methods, not guessed. `openapi-typescript` added as a `frontend` devDependency, `npm run gen:types` script generates `frontend/lib/api-types.ts` from it. Wired into `frontend/lib/api.ts` (login/register/profile/recentQuizzes/weeklyPerformance) and into the highest-traffic components — `frontend/app/quiz/[id]/page.tsx` (attempt start), `frontend/app/results/[attemptId]/page.tsx` (attempt result), `frontend/components/MasteryRecommendations.tsx` (mastery/recommendations) — replacing `any`/ad-hoc inline types with generated ones. `handleResponse`'s default generic changed from implicit `any` to `<T = any>` (explicit) so existing untyped call sites keep compiling unchanged. This is additive/typing-only — no endpoint behavior changed.
- [~] Frontend test suite — **Vitest + React Testing Library set up this session** (spec §10's exact tooling choice); focused tests added for the highest-traffic pieces, not exhaustive/measured coverage — see Testing section below.

## Security (spec §8)
- [x] Argon2id password hashing — `app/core/security.py`, verified via `test_security_helpers.py` and the "Upgrade legacy password hashes to Argon2" commit.
- [x] JWT auth via Flask-JWT-Extended, identity enforced per recent "Enforce JWT identity for personalized quiz endpoints" commit; role/ownership checks (`_can_access`, `require_role`) present on student/teacher resource routes.
- [x] Rate limiting on auth endpoints — see Auth API section above.
- [x] CORS allowlist — `app/main.py`: when `FRONTEND_URL` env var is set, CORS is restricted to that origin with credentials; otherwise (local dev) wide-open without credentials. Matches spec intent for prod.
- [x] Upload validation — 25MB cap + MIME/magic-byte checks (`app/core/uploads.py`), enforced in both `/materials` and `/teacher/materials`.
- [x] PII encryption at rest — **implemented this session**: spec literally names Postgres `pgcrypto`, which is unavailable here (this repo runs SQLite locally/in tests) — a legitimate, documented deviation. Instead, `backend/app/core/encrypted_type.py::EncryptedString` is a dialect-agnostic SQLAlchemy `TypeDecorator` using Fernet (AES + HMAC) that transparently encrypts `users.email`/`users.full_name` on write and decrypts on read, keyed from `PII_ENCRYPTION_KEY` (env var, with an insecure-but-functional dev default + warning log, same pattern as `JWT_SECRET_KEY` in `app/core/config.py`). Since Fernet encryption is non-deterministic, `email` can no longer be matched in a `WHERE` clause, so a new indexed/unique `email_lookup_hash` column (HMAC-SHA256 of the normalized email, keyed by `PII_LOOKUP_HASH_SECRET`, non-reversible) was added and is now used for all login/uniqueness lookups via `User.find_by_email()`. A `before_insert`/`before_update` SQLAlchemy event listener keeps `email_lookup_hash` in sync automatically even for code that still constructs `User(email=...)` directly (tests, `seed_db.py`), so no call site was silently broken. Migration `backend/migrations/versions/e5f6a7b8c9d0_encrypt_pii_email_full_name.py` widens the columns and backfills existing rows (encrypts existing plaintext, computes hashes) — verified manually against a scratch copy of the SQLite dev DB: a plaintext row inserted pre-migration came out as ciphertext post-migration and decrypted correctly via the ORM. Updated call sites: `app/api/v1/auth/routes.py` (register/login), `app/api/v1/teacher/routes.py` (invite_student), plus dev scripts `seed_db.py`/`create_student.py`/`test_personalization.py`/`test_weekly_system.py`. New tests in `backend/app/tests/test_pii_encryption.py` (3 new, passing) assert the raw DB column is not plaintext, that case-insensitive lookup-by-hash works, and that register→login works end-to-end with the encrypted column. `cryptography==50.0.0` added to `backend/requirements.txt`.
- [x] Admin audit log — **implemented this session**: new `audit_log` table (`app/models/audit_log.py::AuditLog` — `id, actor_id (FK users.id), action, target_type, target_id, details, created_at`) + migration `backend/migrations/versions/d3e4f5a6b7c8_add_audit_log.py` (plus `c2d3e4f5a6b7_add_is_admin_to_users.py` adding a `users.is_admin` flag, since no admin role existed yet). `app/services/audit_service.py::log_admin_action()` inserts rows. `app/core/authz.py::require_role('admin')` now auto-logs an entry on every admin-guarded route after the role check passes (so any future admin route is covered automatically — no admin routes existed in the codebase prior to this session, so this hook is the enforcement point); the sensitive "admin views another user's data" action additionally logs a specific `admin_view_user` entry with the target user id (`GET /api/v1/admin/users/:id`). New `GET /api/v1/admin/audit-log` (admin-only, paginated via `page`/`per_page`, ordered `created_at DESC`) lists entries. Tests in `app/tests/test_admin_audit_log.py` (3 new, passing) cover: non-admin/unauthenticated access is rejected, an admin action creates an audit_log row, and the listing endpoint returns entries newest-first. Incidental fix: `app/core/authz.py` imported `verify_jwt_in_request_optional`, which doesn't exist in the installed `flask-jwt-extended` version — this was a pre-existing bug silently masked because `teacher_bp`'s import in `app/main.py` was wrapped in a bare `try/except`, so `require_role` had never actually been exercised; wiring in the new admin blueprint (imported unconditionally) surfaced it. Fixed by switching to `verify_jwt_in_request(optional=True)`, which also un-breaks the previously-silently-disabled `teacher_bp`.
- [x] Role/ownership checks on every v1 resource route — **audited this session, no gaps found**: `students/routes.py` gates all three endpoints through `_can_access(student_id)`; `attempts/routes.py` compares `attempt.user_id` to the JWT identity on responses/submit/result/next-question; `materials/routes.py` compares `material.owner_id` on GET and generate-quiz and requires teacher on create; `classes`/`admin` use `require_role`. No route was found reachable without its check.
- [x] Refresh-token rotation — **verified this session** with new tests: `POST /auth/refresh` revokes the presented token's `jti` and issues a new pair; the consumed token is then rejected (401 via the `token_in_blocklist_loader`), the new one still works, and an *access* token presented to `/auth/refresh` is rejected (422). See `backend/app/tests/test_api_contract.py`.
- [ ] ClamAV virus-scan hook — not implemented (spec marks this "planned", consistent with v1 scope).

## Error Format (spec §4.5)
- [x] Uniform `{"error": {"code","message","details"}}` envelope across **all** endpoints — **implemented this session**. The audit found it was *not* uniform: only a handful of newer v1 handlers emitted the envelope, while most routes (and everything flask-jwt-extended produced) returned `{"msg": "..."}`, which the frontend reads (`frontend/lib/api.ts`, both auth pages, `app/teacher/page.tsx`). Rather than break those clients, `app/main.py` gained a `normalize_error_envelope` `after_request` hook: any 4xx/5xx JSON response that lacks an `error` key is wrapped in place, with the message taken from the existing `msg`/`message`/`description` field (or a per-status default), and the legacy key left untouched alongside it. Handler-supplied envelopes pass through unchanged (no double-wrapping); 2xx responses are untouched. A status→code table (`ERROR_CODES`) plus an `error_response()` helper give consistent codes (`VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `RATE_LIMITED`, `INTERNAL_ERROR`, …). The ad-hoc 404/413 handlers were replaced by a generic `HTTPException` handler (so 405/415/422/etc. are covered too) and a catch-all `Exception` handler that logs a structured JSON line and returns a 500 envelope — the catch-all deliberately re-raises under `app.debug`/`app.testing` so real stack traces are never masked in dev or tests.

## Observability (spec §9)
- [x] `X-Request-ID` correlation IDs — present in `app/main.py` (`before_request` reads the inbound header or generates a UUID; `after_request` echoes it on every response). Verified this session with tests for both the echo and the generate paths.
- [x] Structured JSON request logging — one JSON line per request (`event`, `request_id`, `method`, `path`, `status`, `duration_ms`). Not `structlog` as spec literally names, but the same structured-JSON outcome; test asserts the emitted line parses as JSON with those fields.
- [x] Prometheus `/metrics` endpoint — exists and was **extended this session** with `HELP` lines and a `assesify_responses_by_status_total{status="…"}` series alongside the existing request/error/duration counters. Test asserts the exposition format, the error counter incrementing on a 404, and the per-status label.
  - Incidental fix: `add_cors_headers` in `app/main.py` contained ~10 lines of dead code duplicated *after* its `return response` (metrics/logging written twice, second copy unreachable). Removed.
- [~] OpenTelemetry tracing — **SDK wired 2026-08-26** (`backend/app/core/tracing.py`, opt-in via `OTEL_ENABLED`, span-per-request verified with an in-memory exporter in `app/tests/test_tracing.py`, correlation id copied onto the span). `[B]` for the OTLP collector / Grafana dashboards half — no collector in this environment. Originally recorded as: not implemented; both need external collector/dashboard infrastructure that doesn't exist in this environment, and neither is meaningfully verifiable locally.

## Testing (spec §10)
- [x] Backend unit/integration — `pytest` suite runs clean after fixes made this session.
  - **Before this session**: 3 failed, 2 errors (collection failure blocked the whole run).
  - **After this session**: `26 passed, 0 failed` (`backend/pytest.ini` added to exclude 3 root-level manual smoke scripts — `upload_test.py`, `test_personalization.py`, `test_weekly_system.py` — which hit a live server / require a pre-existing DB and aren't real pytest tests).
  - Fixed: `ml/recommender.py` groupby bug (real bug, not test-only — would have silently broken recommendation aggregation in production whenever `subtopic` is `None`).
  - Fixed: `ml/tests/test_upload_endpoint.py` was stale (referenced a nonexistent legacy route with a hardcoded foreign machine path, no auth) — rewritten to hit the real `/api/v1/materials` endpoint with proper JWT auth; now passes and gives real coverage.
- [~] Backend integration tests against real Postgres — the pytest suite still runs on SQLite, but the app itself is now verified against real Postgres end-to-end (2026-08-26; see the final follow-up entry). Testcontainers-based *automated* PG tests remain unwritten. Originally recorded as: not run — not run; SQLite used throughout (adequate for logic verification, not for Postgres-specific behavior like `GIN` indexes or `TEXT[]` arrays).
- [x] **Frontend unit tests — coverage target met (spec §10, ≥75%)**: `@vitest/coverage-v8` installed, a `coverage` block added to `frontend/vitest.config.mts` (v8 provider, scoped to `app/`, `components/`, `lib/` and excluding `__tests__`, the generated `lib/api-types.ts`, and layout files so the number reflects real application code), and a `npm run test:coverage` script added. **Measured: 80.69% statements / 81.35% lines / 72.22% functions / 65.69% branches**, from `118 tests across 12 files, all passing` (up from 17 tests / 27.69% statements at the start of this session). Full detail in the follow-up session entry below.
- [~] Frontend unit tests (Vitest+RTL) — original setup session. `vitest@4.1.11`, `@testing-library/react@16.3.2` (React-19-compatible), `@testing-library/jest-dom@7.0.1`, `@testing-library/user-event@14`, `@vitejs/plugin-react@6`, `jsdom@30` added as `frontend` devDependencies (chosen over `next/jest` because this project uses Next.js 16.1.1 with Turbopack and no existing Jest config — a Vite-native Vitest setup integrates more directly and doesn't require reconciling Next's Jest SWC transform with Turbopack). `frontend/vitest.config.mts` (`.mts` so Vite's native config loader doesn't warn about CJS/ESM ambiguity) wires `@vitejs/plugin-react`, `jsdom` environment, and the `@/*` path alias from `tsconfig.json`; `frontend/vitest.setup.ts` adds `@testing-library/jest-dom` matchers plus a `ResizeObserver`/`getBoundingClientRect` stub (jsdom implements neither, and Recharts' `<ResponsiveContainer>` needs them to size the chart to non-zero dimensions). `"test": "vitest run"` and `"test:watch": "vitest"` added to `frontend/package.json`. `frontend/tsconfig.json` now excludes `**/__tests__/**` and the vitest config/setup files so `next build`'s TypeScript pass doesn't type-check test-only code.
  - **5 test files, 17 tests, all passing**: `frontend/lib/__tests__/api.test.ts` (`api.login` request shape + 401 auto-logout, `api.getRecentQuizzes` auth header presence/absence — mocked `global.fetch`); `frontend/components/__tests__/MasteryRecommendations.test.tsx` (renders nothing for a teacher account, radar chart renders competency tick labels from mock mastery data, Karmayogi-unavailable banner shows/hides based on `karmayogi_available` — mocked `fetch` + `localStorage`); `frontend/app/quiz/[id]/__tests__/page.test.tsx` (renders question + options, selecting an option enables the Check button, checking an answer autosaves via `POST .../responses` with the correct `question_id`/`selected_keys`, and the final Continue click calls `POST .../submit` — mocked `next/navigation` `useParams` + `fetch`); `frontend/app/(auth)/login/__tests__/page.test.tsx` and `frontend/app/(auth)/register/__tests__/page.test.tsx` (form renders, submit calls the mocked `api.login`/`api.register` with correct args, success path stores token/redirects, failure path shows the error and does not redirect — mocked `@/lib/api` + `next/navigation` `useRouter`).
  - **Superseded by the follow-up session below** — coverage is now measured and the suite is much larger. Kept for history.
  - Verified: `npm test` → `5 passed | 17 passed (17)`. `npm run build` re-run after all test-infra changes → still succeeds (11 routes, same as before). `backend/.venv/Scripts/python.exe -m pytest -q` re-run → still `34 passed, 0 failed` (frontend-only change, no backend files touched).
- [x] **E2E (Playwright) — done 2026-08-26**: `frontend/e2e/quiz-flow.spec.ts` + `frontend/playwright.config.ts`, chromium downloaded and running locally, 2 tests passing against both real servers via `npm run test:e2e`. `[~]` Load tests (Locust): `backend/locustfile.py` authored + validated (`app/tests/test_locustfile.py`), the 500-user run itself `[B]`. See the final follow-up entry. Superseded note below kept for history — originally recorded as: still not attempted; no browser automation runtime or load-testing infra available in this environment, and per the task's scoping guidance these were treated as out-of-scope for a single session rather than stubbed. Both would layer cleanly on top of the app as-is (Playwright against `npm run dev`/`next start`; Locust against the Flask dev server) whenever that infra is available.

---

## Exact test run (this session, final)
```
cd backend && ./.venv/Scripts/python.exe -m pytest -q
26 passed, 1225 warnings in 8.63s
```
(warnings are pre-existing SQLAlchemy/Pydantic/joblib deprecation noise, not failures)

## Follow-up session (2026-08-24): persistence, API base URL, mastery radar
- Implemented `recommendations` table persistence, fixed hardcoded frontend API URLs, and added a Recharts mastery radar chart (see items above, now flipped to `[x]`).
- Backend pytest suite re-run after the persistence change: still `26 passed, 0 failed` — no regressions.
- Incidental fix: `frontend/app/quiz/[id]/page.tsx` had a pre-existing (unrelated to this session's 3 tasks) TypeScript error — `interface Question` was missing an `id` field that the component already referenced — which blocked `npm run build` entirely. Added `id?: string | number` to the interface so the build could complete; this was a pre-existing bug, not introduced this session, but had to be fixed to verify the radar chart change compiles.
- `frontend/package.json` now includes `recharts` as a dependency (installed via `npm install recharts`).
- `npm run build` in `frontend/` succeeds end-to-end (compiles, generates all static/dynamic routes).

## Follow-up session (2026-08-24): admin audit log
- Implemented the admin audit log (spec §8), chosen over PII-at-rest encryption as the higher-priority, more tractable security item this session (see "Security (spec §8)" section above, now flipped to `[x]`).
- Backend pytest suite re-run after the change: `29 passed, 0 failed` (26 pre-existing + 3 new `test_admin_audit_log.py` tests) — no regressions.
- Incidental fix (pre-existing bug, not introduced this session): `app/core/authz.py` referenced a `flask-jwt-extended` function that no longer exists in the installed version; this had been silently swallowed by a bare `try/except` around `teacher_bp`'s import in `app/main.py`, so `require_role` was dead code. Fixed so both the new admin routes and the previously-broken `teacher_bp` work correctly.

## Follow-up session (2026-08-24): PII encryption at rest
- Implemented application-level PII encryption for `users.email`/`users.full_name` (spec §8), the remaining unmarked security item — see "Security (spec §8)" section above, now flipped to `[x]`, for full detail on the SQLite-vs-pgcrypto approach and the `email_lookup_hash` workaround for login/uniqueness lookups.
- Backend pytest suite re-run after the change: `32 passed, 0 failed` (29 pre-existing + 3 new `test_pii_encryption.py` tests) — no regressions.
- Added `cryptography==50.0.0` to `backend/requirements.txt` (installed into `backend/.venv`) and a new migration `e5f6a7b8c9d0_encrypt_pii_email_full_name.py`, verified by manually running it against a scratch copy of the dev SQLite DB with a pre-existing plaintext row, confirming the backfill correctly produces ciphertext + a matching lookup hash and that the ORM decrypts it back to the original value.
- Noted but out of scope: `backend/migrations/versions/` already had two divergent, unmerged heads (`76d4ba2e9c10` and `840eb69db66d`) before this session — a pre-existing issue confirmed via `git stash` (reproduces without this session's changes), not something this session introduced or fixed. `flask db upgrade head` will fail with "Multiple head revisions" until that's resolved; not required for this task since tests use `db.create_all()` rather than migrations.

## Follow-up session (2026-08-24): unified legacy JSON-blob quiz path onto the relational schema
- Unified the `quizzes`/`questions` data-model split (see Data Model section above, now `[x]`) and the `POST /teacher/materials` legacy-duplicate note (Materials & Generation API section, now `[~]` with the storage-format divergence resolved). Three write sites changed: `app/api/v1/teacher/routes.py::upload_material`, `app/api/v1/lessons/routes.py::generate_lesson_quiz`, `app/api/v1/materials/routes.py::generate_material_quiz` — all now call the new `app/services/quiz_generation.py::persist_quiz_questions()` helper to create relational `Question` rows, and none of them write to `Quiz.questions` any more (`Quiz(questions=[])`).
- `app/models/quiz.py::Quiz.to_dict()` now derives its `questions` field from relational `Question` rows (via `quiz_generation.legacy_shape_from_questions()`) when present, falling back to the raw JSON blob only for quizzes with no relational rows. `app/api/v1/quizzes/routes.py::get_recent_quizzes` similarly counts relational rows first. This keeps `GET /api/quizzes/:id` (consumed directly by `frontend/app/quiz/[id]/page.tsx`) returning the exact same JSON shape as before — verified via `npm run build` (unchanged, no frontend edits needed) and grep confirming no other frontend code reads `Quiz.questions` in a JSON-blob-specific way.
- **Trade-off taken (documented per the task's conservative-default guidance)**: `quizzes.questions` JSON column is kept, not dropped — it's now a deprecated, read-only fallback for legacy data rather than dropping it and risking data loss on a column no migration can prove is fully backfilled everywhere. A new Alembic migration, `migrations/versions/b2c3d4e5f6a7_backfill_legacy_quiz_questions.py` (revises `c34d7f13f504`, the prior single head), backfills `Question` rows from the JSON blob for any existing quiz that has blob content but no relational rows yet, so old data becomes fully relational without waiting for a lazy on-read backfill. Verified two ways: (1) `flask db upgrade head` run end-to-end against a scratch copy of `assesify_dev.db` (13 -> 15 migrations, ending at `b2c3d4e5f6a7`, no errors) confirming the migration chain itself is sound — note the *content* of that particular scratch copy had zero legacy quiz rows to backfill by the time this migration runs (quizzes on that specific dev DB predate the relational `questions` table entirely and are pre-migration test fixtures), so a separate (2) isolated unit exercise of the migration's `upgrade()` function against a synthetic SQLite db with one legacy JSON-blob quiz and one already-relational quiz confirmed it backfills the legacy one correctly (`stem`, `options` with lettered keys, `correct_keys`, `explanation`) and correctly skips the quiz that already had relational rows (no duplication). `backend/assesify_dev.db` itself was never modified — all runs used disposable copies under `instance/`, deleted after.
- `app/services/quiz_generation.py` is new: `persist_quiz_questions()` (the single write-path mapping from generator-dict shape to `Question` rows, replacing three near-duplicate inline copies) and `legacy_shape_from_questions()` (the read-path inverse, used by `Quiz.to_dict()`).
- Deferred/residual: `app/services/personalized_quiz_service.py` (personalized + weekly-test quiz generation, reached via `POST /quizzes/generate-personalized` and `/generate-weekly-test`) still writes only `Quiz.questions` JSON blob and was intentionally left unconverted — its submission flow (`POST /quizzes/:id/submit`) scores client-supplied `{question, answer}` text pairs rather than question ids, a materially different attempt model from the id-based `Response`/`Question` flow used by `attempts_bp`. Converting it would mean redesigning that submission contract, which was judged out of scope for this session; it continues to work exactly as before (mastery still updates correctly for it via `mastery_service`'s existing legacy-attempt-score fallback path, unchanged).
- New tests: `backend/app/tests/test_legacy_quiz_unification.py` (2 new) — asserts `POST /api/v1/teacher/materials` creates `Question` rows tagged with the request's `subject`, leaves `Quiz.questions` empty, and that `Quiz.to_dict()` reflects the relational data; and that a quiz with no relational rows still falls back to its JSON blob correctly.
- Backend pytest suite re-run after the change: `34 passed, 0 failed` (32 pre-existing + 2 new) — no regressions. `npm run build` in `frontend/` re-run after: succeeds unchanged (11 routes generated, same as before).

## Follow-up session (2026-08-24): OpenAPI-generated TS types
- Implemented spec §7.3's shared OpenAPI schema → generated TS types (see Frontend section above, now `[x]`). No existing OpenAPI/Swagger setup was found in the backend, so `backend/openapi.yaml` was hand-authored to describe the API as it actually behaves today (read every route handler and model `to_dict()` involved, not guessed), covering the core resources spec.md §4 lists — not exhaustive on every edge case (legacy/duplicate endpoints like `/teacher/analytics`, `/teacher/materials` are covered at a basic level; deeply nested error-response variants are not modeled per-endpoint, a single shared `Error` schema is reused instead).
- `openapi-typescript@7.13.0` added to `frontend/package.json` devDependencies (`npm install -D openapi-typescript`), new script `"gen:types": "openapi-typescript ../backend/openapi.yaml -o lib/api-types.ts"`, run to produce `frontend/lib/api-types.ts` (auto-generated, not hand-edited).
- Wired into `frontend/lib/api.ts` (login, register, getClasses, updateProfile, getProfile, getRecentQuizzes, getWeeklyPerformance) and three components/pages: `frontend/app/quiz/[id]/page.tsx`, `frontend/app/results/[attemptId]/page.tsx`, `frontend/components/MasteryRecommendations.tsx` — prioritized per the task's guidance (auth, quizzes, attempts, students/mastery/recommendations) rather than converting every fetch call in the app (e.g. `getTeacherAnalytics`, the legacy `/quiz/[id]` question shape which is a UI-side derived shape distinct from the raw `Question` schema, and class/teacher-invite call sites were left as-is).
- Iterated the schema twice after the first `npm run build` surfaced real gaps versus the hand-authored spec: added a missing `karmayogi_available` field to the `Recommendation` schema (present on the backend's internal-fallback recommendation, `app/services/karmayogi_service.py::_internal_fallback`, but initially omitted from the spec) and added `required` field lists to several response schemas (`User`, `Question`, `RecentQuiz`, `MasteryRow`, `Gap`, `Recommendation`, `StartAttemptResponse`, `SaveResponseResult`, `SubmitAttemptResponse`, `AttemptResult`) since `openapi-typescript` makes every property optional by default without an explicit `required` list, which doesn't match what these always-populated Flask response dicts actually return.
- Verified: `npm run build` in `frontend/` succeeds (all 11 routes generate, both static and dynamic). `backend/.venv/Scripts/python.exe -m pytest -q` re-run after: still `34 passed, 0 failed` — this change is frontend + a static YAML file, backend code untouched, no regression expected or found.

## Follow-up session (2026-08-24): fixed diverged Alembic migration heads
- Fixed the migration-heads issue noted above as out-of-scope in the prior session — see "Alembic migration heads" item in the Data Model section (now `[x]`). Turned out to be **three** divergent heads, not two, plus a second independent bug (unnamed FK constraint breaking SQLite batch-mode migrations). `flask db upgrade head` now succeeds cleanly; `spec.md` §11.2's documented bootstrap flow (`uv run flask db upgrade`) is unblocked.
- Backend pytest suite re-run after the fix: `32 passed, 0 failed` — no regressions.
- Did not touch `backend/assesify_dev.db`; all verification used a disposable scratch SQLite file that was deleted afterward.

## Follow-up session (2026-08-24): frontend unit testing (Vitest + RTL)
- Set up the spec §10-mandated frontend test runner from scratch — see "Frontend unit tests (Vitest+RTL)" in the Testing section above (now `[~]`) for the full package/config breakdown and file-by-file test list. Checked `frontend/package.json` (Next.js 16.1.1, React 19.2.3, TypeScript strict, Tailwind v4, no prior Jest/Vitest config) before adding anything.
- Added `frontend/vitest.config.mts`, `frontend/vitest.setup.ts`, and 5 test files (17 tests total, all passing) covering: `lib/api.ts` (login request shape, 401 handling, auth-header presence), `components/MasteryRecommendations.tsx` (radar chart data rendering, Karmayogi-fallback banner show/hide), `app/quiz/[id]/page.tsx` (question rendering, option-select state, autosave + final-submit API calls), and both `app/(auth)/login` and `app/(auth)/register` pages (render, submit, success/failure paths) — no components or pages were redesigned, only existing behavior exercised against mocked `fetch`/`@/lib/api`/`next/navigation`.
- Non-trivial fix along the way: Recharts' `<ResponsiveContainer>` (used by the mastery radar) measures its container via `ResizeObserver` + `getBoundingClientRect`, neither of which jsdom implements — without a stub the chart renders at 0×0 and no chart content exists to assert on. `vitest.setup.ts` installs a `ResizeObserver` stub that synchronously invokes its callback with fixed dimensions, plus a `getBoundingClientRect` override, which fixed it.
- Also fixed a build break the new test files introduced: `next build`'s TypeScript pass was type-checking `vitest.setup.ts` and the `__tests__` folders by default (tsconfig had no exclude for them), tripping on an unused `@ts-expect-error`. Removed the now-unnecessary directive and added `**/__tests__/**`/`vitest.config.mts`/`vitest.setup.ts` to `frontend/tsconfig.json`'s `exclude` so production type-checking stays scoped to app code.
- Verified in order: `npm test` → `5 passed | 17 passed (17)`; `npm run build` → succeeds, same 11 routes as before; `backend/.venv/Scripts/python.exe -m pytest -q` → still `34 passed, 0 failed` (no backend files touched).
- Deliberately not attempted: Playwright E2E and Locust load tests (spec §10) — no browser-automation or load-testing infrastructure available in this environment; left as `[ ]` rather than stubbed, per the task's scoping guidance. A formal coverage percentage against the spec's "≥75%" target was not measured (`@vitest/coverage-v8` not installed) — this session prioritized a focused, realistic set of tests over instrumenting a coverage gate.

## Follow-up session (2026-08-24): Karmayogi OAuth2/PKCE, error envelope + observability, frontend coverage
Deep audit of every `[ ]`/`[~]` item against the actual code, then four workstreams. Audit corrections made: observability (spec §9) was entirely unrepresented in this file despite `/metrics`, `X-Request-ID`, and JSON request logging already existing in `app/main.py` — a new "Observability" section now tracks it honestly; the error-envelope requirement (§4.5) was likewise untracked and turned out to be genuinely non-uniform; role/ownership checks and refresh-token rotation were marked `[x]` on inspection only and are now backed by tests.

1. **Karmayogi OAuth2 (spec §6.1)** — implemented both flows: client-credentials for server-to-server catalog calls (with an in-process token cache) and authorization-code + PKCE for user-consented identity linking, backed by a new server-side `oauth_states` table so the `code_verifier` never reaches the client. Two new endpoints, a new model + migration, a new service module, and 18 mocked-HTTP tests covering challenge derivation, state validation/CSRF and replay rejection, cross-user rejection, expiry, token exchange, userinfo fallback, provider errors, and the unconfigured-deployment path. Full detail in the Auth API and Karmayogi Integration sections above. Migration verified with `flask db upgrade head` against a scratch SQLite DB (16 migrations, single head `f6a7b8c9d0e1`, `oauth_states` created); `backend/assesify_dev.db` untouched, scratch file deleted.
2. **Error envelope + observability** — see the new "Error Format (spec §4.5)" and "Observability (spec §9)" sections. 13 new tests in `backend/app/tests/test_api_contract.py`. Removed ~10 lines of unreachable duplicated code in `app/main.py`'s `after_request`.
3. **Personalized/weekly quiz service → relational schema** — (superseded by the 2026-08-26 follow-up below, which completed this) inspected and **deliberately left as-is** at the time, confirming the prior session's assessment rather than overriding it. `POST /quizzes/:id/submit` (`app/api/v1/quizzes/routes.py`) accepts `{"answers": [{"question": "<text>", "answer": "...", "is_correct": true}]}` — client-supplied correctness keyed by question *text*, with no question ids anywhere in the contract. Converting the generator to write relational `Question` rows would also change what `Quiz.to_dict()` returns for these quizzes (it prefers relational rows over the JSON blob), altering the payload the quiz-taking page consumes. That is a breaking redesign of both the submission contract and the frontend, so per the task's conservative default it stays `[~]` with this honest note.
4. **Frontend coverage (spec §10, ≥75%)** — installed `@vitest/coverage-v8`, configured a scoped coverage block, and measured a real baseline of **27.69% statements**. Added 7 new test files / 101 new tests: `lib/__tests__/api.client.test.ts` (22 — every remaining `api.*` wrapper's URL/method/body/headers, token+user storage round-trips, FormData calls that must omit `Content-Type`, and the full `handleResponse` error ladder incl. 401/422 auto-logout vs. a 404 leaving auth intact), `components/__tests__/ui.test.tsx` (19 — `Button` variants/disabled, `Card` padding/class-merge, `ProgressBar` clamping/colour, `MobileNav` active-route highlight, `Sidebar` student-vs-teacher nav + avatar/initial fallbacks, `TopicsToReview` list/empty/limit/open-file/fetch-failure), `components/__tests__/modals.test.tsx` (12 — create/join/invite modals: closed renders nothing, validation gating, success and failure paths, cancel), `components/__tests__/TeacherUploadModal.test.tsx` (11 — the whole upload→config→generating→success state machine incl. drag-and-drop, Remove, Back, the exact `FormData` submitted, and the failure path returning to config), `app/dashboard/__tests__/page.test.tsx` (16 — student vs teacher views, gamification stats, weekly-test panel and generation, class list/empty states, modal wiring, all-APIs-failing resilience), `app/teacher/__tests__/page.test.tsx` (10 — class cards, analytics links, upload/create-class modals, the inline invite form incl. the no-token guard), `app/profile/__tests__/page.test.tsx` (12 — fetch+cache, edit/save/cancel, avatar upload success and failure, logout redirect, teacher-hidden sections). **Final measured: 80.69% statements, 81.35% lines, 72.22% functions, 65.69% branches — target met.**

### Two real pre-existing frontend bugs found and fixed by the new tests
- `app/dashboard/page.tsx` — `fetchWeeklyPerformance()` read the `user` **state** variable, but its only caller runs in the same `useEffect` tick as `setUser(u)`, so `user` was still `null` and the function always returned early. The weekly-performance panel could therefore *never* render its data; students only ever saw the "No quiz activity this week yet" empty state. Fixed by passing the user object in explicitly (`fetchWeeklyPerformance(u)`), defaulting to the state value for any later call.
- `app/teacher/page.tsx` — the invite result message (`inviteMsg`) was rendered *inside* the `{isInviteOpen && …}` block, but a successful invite sets `setIsInviteOpen(false)`, unmounting the message in the same render. The success confirmation was therefore never visible. Moved the message outside the collapsible block.

### Verification (run after every workstream, and again at the end)
- `backend/.venv/Scripts/python.exe -m pytest -q` → **65 passed, 0 failed** (34 pre-existing + 18 `test_karmayogi_oauth.py` + 13 `test_api_contract.py`).
- `cd frontend && npm test` → **12 files, 118 tests passed, 0 failed** (17 pre-existing + 101 new).
- `cd frontend && npm run test:coverage` → **80.69% statements / 81.35% lines / 72.22% functions / 65.69% branches**.
- `cd frontend && npm run build` → succeeds, 14 route entries generated (unchanged set).
- `backend/openapi.yaml` gained the two new auth endpoints; `npm run gen:types` re-run and the build re-verified afterwards.
- Nothing committed or pushed; no destructive git operations; `backend/assesify_dev.db` never modified.

### Still open after this session
- ~~`[~]` `personalized_quiz_service.py` relational conversion~~ — **done 2026-08-26**, see the final follow-up entry.
- `[ ]` Playwright E2E, Locust load tests, OpenTelemetry/Grafana — all need infrastructure absent from this environment.
- `[ ]` ClamAV upload scanning — spec itself marks it "planned", out of v1 scope.
- `[B]` Live Gemini, live Karmayogi sandbox, real Postgres — external credentials/services; all local code paths, mocks, and fallbacks verified instead.

## Pre-commit review (2026-08-24)

Full working-tree diff reviewed against spec.md before committing. Verified clean:

- **Migration ordering** — traced every `revision`/`down_revision` pair by hand.
  Chain is linear from root `13c5dff61063` to a single head `f6a7b8c9d0e1`; the
  merge node `c34d7f13f504` correctly references all three former branch tips
  (`76d4ba2e9c10`, `840eb69db66d`, `e5f6a7b8c9d0`). No orphans, no second head.
- **API compatibility** — the §4.5 error-envelope normalizer *adds* an `error`
  key while preserving the legacy `msg`/`message` keys the frontend reads, so
  existing clients are unaffected.
- **Security** — `.env` is gitignored and untracked; no hardcoded API keys or
  secrets in any new/modified source file; the catch-all exception handler
  re-raises under debug/testing and returns a generic 500 otherwise (no stack
  traces leaked); admin routes are audit-logged and audit failures can never
  break the underlying action.
- **Tests/build consistency** — backend 65 passed, frontend 118 passed,
  `npm run build` succeeds (11 routes). New `admin` blueprint package has its
  `__init__.py`, matching the other `api/v1/*` packages.

Two real issues found and fixed (fixes only, no feature work):

1. **Incidental binary churn** — `backend/ml/models/{algebra,calculus,geometry}.joblib`
   showed as modified. Cause: `ml/topic_models.py` retrains and `joblib.dump()`s
   these on every test run, so the suite rewrites them (a ~16-byte metadata
   delta, not a real model change). Reverted. **Note for whoever commits:** the
   suite re-dirties these on each run, so revert them again immediately before
   `git add`. Longer-term these tracked build artifacts should be untracked and
   gitignored — deliberately left alone here as out of scope for a review pass.
2. **Test-run upload artifacts** — 34 untracked files under `backend/uploads/`
   generated by dev/test runs were staged to be swept into the commit. Added
   `backend/uploads/*.txt`, `*.pdf`, and `avatars/` to `.gitignore`. Pre-existing
   tracked uploads are unaffected (still tracked); only new artifacts are ignored.

Known pre-existing repo-hygiene issues, **not** introduced by this work and left
untouched: `backend/assesify_dev.db` is tracked in git (it was not modified by any
of this work), and the `ml/models/*.joblib` artifacts described above.

**Verdict: GO for commit.**

## Follow-up session (2026-08-26): personalized/weekly quizzes → relational Question schema

Completed the one remaining `[~]` item that two prior passes had deferred: `app/services/personalized_quiz_service.py` was the last code in the repo still writing questions into the deprecated `quizzes.questions` JSON blob. It now writes relational `Question` rows like every other generator path, and `POST /api/quizzes/:id/submit` gained **additive** server-authoritative scoring.

### Write path (spec §3.1 `questions`, §5.1 step 6)
Four blob write sites were converted (the task brief named two; tracing the file end to end found four) — all now `QuizModel(..., questions=[])` → `db.session.flush()` → the existing shared `app/services/quiz_generation.py::persist_quiz_questions()` helper → `commit()`. No new helper and no third code path were introduced.
1. `generate_personalized_quiz()` empty-history fallback (rule-based `ml.train.quiz_gen.generate_quiz`) — tagged with the lesson's topic.
2. `generate_personalized_quiz()` Gemini branch (`generate_quiz_from_action`, `choices`→`options` normalization unchanged) — tagged with the recommended action's topic.
3. `generate_weekly_test()` no-activity fallback — tagged with the lesson's topic.
4. `generate_weekly_test()` main multi-topic branch — questions are grouped by their `topic` metadata and persisted per group, so each question carries **its own** competency tag rather than a single blanket one. This is what makes weekly-test responses attributable in mastery/gap analysis (spec §5.2).

`Quiz.to_dict()` was already relational-first, so `GET /api/quizzes/:id` returns byte-identical JSON to before and **no frontend change was required** — confirmed by `npm test` and `npm run build` both passing untouched.

### Submit / scoring contract — additive, legacy preserved
`POST /api/quizzes/:id/submit` previously trusted client-supplied `{question, answer, is_correct}` outright. It now grades each answer *before* computing the score: when an answer carries `question_id` matching a `Question` row **on that quiz**, correctness is computed server-side by `_grade_against_question()` (accepts `selected_keys`, or falls back to mapping the literal `answer` text back to an option key) and the client's `is_correct` is ignored; `question_text` is then taken from the stored `stem`. When `question_id` is absent the legacy path is used verbatim. Gamification (health/streak/diamonds), the response body, and `refresh_student_mastery()` are all unchanged.

**Honest limitation:** the frontend does not yet send `question_id` on this endpoint. `frontend/app/quiz/[id]/page.tsx::submitQuiz` posts `answer: "Submitted via API"` with an *approximated* `is_correct` (`i < finalStats.correct`) — it never sends the student's actual selection. Turning on text-based server-side grading unconditionally would therefore score every legacy submission 0%, so id-based grading is strictly opt-in. Wiring the frontend to send `question_id`/`selected_keys` (which requires `legacy_shape_from_questions()` to start emitting `id`) is the natural next step and is deliberately **not** done here — it changes a working user-facing flow.

### Incidental fixes (both caused by the blob no longer being populated)
- `get_weekly_performance()` sized attempts with `len(quiz.questions)`, which would silently become `0` for every relationally-stored quiz. Added `Quiz.question_count()` (relational count, blob fallback) and used it in both places.
- The same function then hit a genuine `ZeroDivisionError` in its `weight` calculation whenever `max_time` was 0 (an empty quiz). Latent before, near-certain after — `max_time` now falls back to 300s. Caught by the new tests, not by inspection.

### Alembic
**No migration added — none is needed.** This change touches write paths only; no column, table, or constraint changed. Existing personalized/weekly quizzes that still hold blob questions are already covered by the prior `b2c3d4e5f6a7_backfill_legacy_quiz_questions` migration, which backfills `Question` rows for *any* quiz with blob content and no relational rows regardless of which service created it (verified by re-reading its `upgrade()`). Single head remains `f6a7b8c9d0e1`.

### Tests
New `backend/app/tests/test_personalized_quiz_relational.py` (6 tests, conventions copied from `test_legacy_quiz_unification.py`, all Gemini calls monkeypatched — no credentials, no network): relational rows for each of the three distinct generation branches with the correct `competency_tag`, blob left empty, `to_dict()` still emitting exactly `{question, options, correct_answer, answer, hint}`; `choices`→`options` normalization and lettered `correct_keys` derivation on the Gemini branch; server-side scoring overriding a client that lies `is_correct: true` (50%, not 100%); and the legacy payload still scoring and persisting `QuizAnswer` rows exactly as before.

### Verification
- `backend/.venv/Scripts/python.exe -m pytest -q` → **71 passed, 0 failed** (65 pre-existing + 6 new).
- `cd frontend && npm test` → **12 files, 118 tests passed** (unchanged).
- `cd frontend && npm run build` → succeeds, same 14 route entries.
- `backend/openapi.yaml`'s `LegacySubmitQuizRequest` documents the optional `question_id`/`selected_keys` fields; `npm run gen:types` re-run and the build re-verified after.
- `backend/ml/models/*.joblib` churn from the test run reverted; nothing committed or pushed; `backend/assesify_dev.db` untouched.

## Follow-up session (2026-08-26): wired the real `question_id` through the frontend

Closes the "honest limitation" left open by the entry above: server-authoritative
grading existed on the backend but nothing ever exercised it, because the read
shape the frontend consumes carried no question id.

### The latent bug that was actually live (not merely dormant)
`quiz_generation.legacy_shape_from_questions()` emitted only
`{question, options, correct_answer, answer, hint}` — no `id`. So on every
relationally-stored quiz, `frontend/app/quiz/[id]/page.tsx::saveResponse()`
hit its `if (!attemptId || !question.id) return;` guard and the autosave POST
to `/api/v1/<attempt>/responses` **never fired at all**. The existing frontend
test did not catch this because its fixture hand-supplies `id: 101`, a value the
real API never returned. (Had the guard not existed, the endpoint would have
rejected the payload anyway: `save_response()` returns
`400 VALIDATION_ERROR` when `question_id` is falsy.)

### Changes
1. **`backend/app/services/quiz_generation.py`** — `legacy_shape_from_questions()`
   now emits `"id": question.id`. Purely additive; every pre-existing key and
   value is unchanged. Two existing tests asserted the exact key set and were
   updated to include `id` (`test_legacy_quiz_unification.py`,
   `test_personalized_quiz_relational.py`).
2. **`frontend/app/quiz/[id]/page.tsx`** — payload-level only, no visual or
   interaction change. `submitQuiz()`'s legacy `POST /api/quizzes/:id/submit`
   body now carries, per question, `question_id` (when the question has one) and
   `selected_keys` derived from the student's **actual** stored selection in
   `answersMap`, plus `answer` set to the real chosen option text instead of the
   `"Submitted via API"` placeholder. The legacy `question`/`is_correct` fields
   are still sent alongside, so a quiz with no relational rows (or any older
   client) scores exactly as before — the backend prefers `question_id` and
   ignores the client's `is_correct` only when it is present. A small
   `optionKeyFor()` helper replaces the duplicated text→key mapping that
   `saveResponse()` already had.
3. **`backend/openapi.yaml`** — the `Quiz` schema's `questions` array previously
   `$ref`'d the *relational* `Question` schema, which is not what
   `GET /api/quizzes/:id` returns. Added an accurate `LegacyQuizQuestion` schema
   (including the new `id`) and pointed `Quiz.questions` at it.
   `npm run gen:types` re-run; build re-verified.

### Deliberate scope calls (conservative default)
- **Auth header added to the legacy submit call only.** The page sends no
  `Authorization` header anywhere, and `POST /api/quizzes/:id/submit` is
  `@jwt_required()` with `JWT_TOKEN_LOCATION = ["headers"]` — so today that
  submit silently 401s and server-side grading could never engage no matter what
  payload was sent. `submitQuiz()` now attaches `Bearer <token>` from
  `getToken()` when one exists. **The attempt-start call was deliberately left
  unauthenticated**: adding a token there would make `attemptId` non-null, which
  would flip `submitQuiz()` onto the entirely different `/api/v1/<id>/submit`
  attempts path (different scoring source, no gamification) — a behavioural
  change well beyond a payload fix. Consequence, stated honestly: the autosave
  path still does not fire in production because `attemptId` stays null; the
  `id` it needs is now available, so wiring auth into attempt-start is a
  single-line follow-up whenever that path switch is intended.
- No UX change: no new screens, no markup or styling touched.

### ~~Remaining integrity gap (spec §8) — `correct_answer` is still shipped to the client~~ — **CLOSED**, see the 2026-08-26 follow-up at the end of this file
`legacy_shape_from_questions()` continues to include `correct_answer` (and the
explanation) in the payload of `GET /api/quizzes/:id`, which is **unauthenticated**.
A student can therefore read every correct answer straight out of the network
response before answering. It was **not** removed in this pass because the
quiz-taking page uses it for immediate per-question feedback (the green/red
option highlight and the "Correct!/Incorrect" footer are computed entirely
client-side from it), so removing it would break the working UX. This is now
**partially mitigated**: the *score of record* no longer depends on it, because
the server recomputes correctness from the stored `correct_keys` whenever
`question_id` is present — which, as of this session, it always is. Closing the
gap properly means a sanitized read endpoint plus a server round-trip for
per-question feedback (`/api/v1/<attempt>/responses` already returns
`is_correct` and would serve exactly that), which is a UX-affecting redesign.

### Tests added
- `backend/app/tests/test_question_id_wiring.py` (4 new, conventions from
  `test_personalized_quiz_relational.py`, no Gemini/credentials/network):
  the legacy shape exposes ids matching the relational rows with all legacy keys
  intact; that served id round-trips into `/api/v1/<attempt>/responses`
  (`200`, `is_correct` computed server-side); the exact payload the frontend now
  sends is graded server-side and **overrides a lying client in both directions**
  (a right answer flagged `is_correct: false` and a wrong answer flagged
  `is_correct: true` → 50%, not 0% or 100%); and a payload with no `question_id`
  still scores off the client flags exactly as before.
- `frontend/app/quiz/[id]/__tests__/page.test.tsx` (2 new): the submit body
  carries the real `question_id`, `selected_keys: ["B"]` and `answer: "Berlin"`
  for the option the student actually picked; and a question with no `id` still
  produces the legacy body with no `question_id` key. `setupFetchMock()` gained
  optional `attemptOk`/`question` overrides so the legacy submit branch can be
  exercised (existing call sites unchanged).

### Verification
- `backend/.venv/Scripts/python.exe -m pytest -q` → **75 passed, 0 failed**
  (71 pre-existing + 4 new).
- `cd frontend && npm test` → **12 files, 120 tests passed, 0 failed**
  (118 pre-existing + 2 new).
- `cd frontend && npm run build` → succeeds, same route set as before.
- `backend/ml/models/*.joblib` churn from the test run reverted; nothing
  committed or pushed; `backend/assesify_dev.db` untouched.

---

## Follow-up session (2026-08-26): closed the `correct_answer` exposure gap

Closes the "Remaining integrity gap" flagged in the entry above. The invariant
now enforced: **a student never receives the correct answer for a question they
have not answered.** Immediate per-question feedback still works, unchanged
visually.

### Design chosen: sanitize the read, reveal one question at a time on commit
Rejected "just delete the field" — `frontend/app/quiz/[id]/page.tsx` read
`currentQuestion.correct_answer` in eight render paths (option highlighting,
the Correct!/Incorrect footer, the footer tint, the Continue button variant and
class) plus `currentQuestion.answer` for the explanation panel. Deleting the
field blind would have silently degraded every one of them to "always
incorrect".

Instead:

1. **`backend/app/services/quiz_generation.py`** — `legacy_shape_from_questions()`
   takes `include_answers`, **defaulting to `False`** (safe by default). The
   sanitized item is exactly `{id, question, options, hint}`; `correct_answer`
   and `answer` (the explanation) are *omitted*, not nulled, so a leak is
   impossible to miss in a test. New `redact_legacy_blob()` applies the same
   strip to the deprecated `Quiz.questions` JSON-blob fallback, so the invariant
   holds on **every** read path rather than only the relational one.
2. **`backend/app/models/quiz.py`** — `Quiz.to_dict(include_answers=False)`
   threads the flag through both the relational and blob branches.
3. **`backend/app/api/v1/quizzes/routes.py`** — `GET /api/quizzes/:id` is now
   role-aware (spec §4.3 "Full quiz (teacher view) or sanitized (student)").
   `_may_see_answers()` reveals answers only to a teacher who owns the quiz's
   lesson, mirroring the `_teacher_owns()` check that
   `app/api/v1/quiz_api/routes.py` already used for the v1 read endpoint.
   Authentication stays *optional* on this route — it has always accepted
   anonymous callers, and an anonymous caller simply gets the student view — so
   no working flow 401s that did not before.
4. **New endpoint `POST /api/quizzes/<quiz_id>/questions/<question_id>/check`**
   (`@jwt_required()`). Body `{"selected_keys": ["B"]}` or `{"answer": "<text>"}`;
   returns `{question_id, is_correct, correct_answer, correct_keys, explanation}`
   **for that one question only**. It reuses the existing
   `_grade_against_question()` so feedback and the score of record can never
   disagree. It **records nothing** — no attempt, no response row — so it cannot
   interfere with the attempts path or with gamification.
5. **`frontend/app/quiz/[id]/page.tsx`** — new `feedbackMap` state keyed by
   question. `handleCheck()` is now async: it saves the response as before,
   enters review mode *immediately* (so the UI never stalls on the round-trip),
   then fills in `feedbackMap[qKey]` from `/check` and awards XP from the
   **server's** `is_correct` rather than a client-side string compare. Every
   former `currentQuestion.correct_answer` read became `currentFeedback?.…`;
   the explanation panel prefers `currentFeedback.explanation`. The green/red
   reveal is gated on `currentFeedback !== undefined`, so a pending or failed
   round-trip shows neutral styling instead of falsely marking a right answer
   wrong. `submitQuiz()` now sends the server-confirmed `is_correct` when it has
   one (still ignored server-side whenever `question_id` is present).
   `Question.correct_answer`/`answer` became optional in the TS interface.
6. **`backend/openapi.yaml`** — `LegacyQuizQuestion.required` drops
   `correct_answer`/`answer` (documented as owning-teacher-view only); new
   `CheckAnswerRequest`/`CheckAnswerResponse` schemas and the
   `/quizzes/{quiz_id}/questions/{question_id}/check` path. `npm run gen:types`
   re-run; build re-verified.

**The score of record was not touched.** `POST /api/quizzes/:id/submit` and the
attempts path both still recompute correctness server-side from the stored
`correct_keys`; a test pins this explicitly (client lies about both answers,
score is still 50%).

### Graceful-degradation choices (documented rather than risked)
- **Blob-only quizzes** (no relational `Question` rows) are sanitized too, but
  cannot use `/check` because it resolves a real `Question` row. Their questions
  carry no `id`, so the page skips the round-trip and falls back to a local
  comparison that now finds no `correct_answer` — feedback degrades to
  "incorrect, no explanation". Accepted because migration
  `b2c3d4e5f6a7_backfill_legacy_quiz_questions` backfills `Question` rows for
  *every* blob quiz, so this branch is unreachable on a migrated database. The
  alternative (index-addressed pseudo-ids) would have leaked into the autosave
  and submit payloads for no real-world gain.
- **A failed or 401 `/check` call** falls back to the same local comparison and
  still advances to review mode with a working Continue button; it never blocks
  the student.

### Residual weakness (honest)
`/check` is unmetered: a determined student could POST an arbitrary guess for
every question up front and harvest the answer key before answering, then
re-submit. This is inherent to any immediate-feedback design that does not bind
feedback to a recorded attempt. Closing it means making `/check` write through
an attempt (first selection wins), which needs an `attempt_id` the page does not
currently have — see the still-open attempt-start auth note below. What *is*
closed is the passive leak: the answers no longer sit in the quiz payload.

### Still open (carried forward, unchanged)
The attempt-start call in `page.tsx` still sends no `Authorization` header, so
`attemptId` stays null in production and the autosave path never fires. Left
alone for the same reason as the previous session: authenticating it flips
`submitQuiz()` onto the `/api/v1/<id>/submit` attempts path, which scores from a
different source and skips gamification.

### Task B — frontend fixture drift audit
Audited `frontend/app/quiz/[id]/__tests__/`, `frontend/lib/__tests__/`,
`frontend/components/__tests__/` and the `app/*/__tests__/` page suites against
`backend/openapi.yaml` and the real serializers.

**Fixed (real, behaviour-relevant drift):**
- `app/quiz/[id]/__tests__/page.test.tsx` — the fixture supplied
  `correct_answer` and `answer`, which the sanitized student payload does not
  return. Same failure mode as the `id: 101` bug the previous session found:
  a test green against a payload production never sends. The fixture is now the
  real sanitized shape, with a separate `CHECK_FEEDBACK` fixture for the
  `/check` response, and a comment warning against adding answers back.
- Same file — the `GET /api/quizzes/:id` mock returned only `{questions}`. It
  now returns the full `Quiz.to_dict()` envelope (`id`, `lesson_id`,
  `questions`, `created_at`).
- Same file — **no test asserted an `Authorization` header on any call**, the
  exact hole that let the silently-401ing submit ship. The suite now stores a
  token and asserts `Bearer test-token` on both the `@jwt_required` `/check`
  and legacy `/submit` calls.
- `components/__tests__/MasteryRecommendations.test.tsx` — mastery rows omitted
  `updated_at` and recommendations omitted `score`/`source`/`course_id`, all of
  which `CompetencyMastery.to_dict()` and `karmayogi_service` always return and
  all of which are `required` in the OpenAPI schemas. Fixtures completed.

**Found, deliberately not changed:**
- `lib/api.ts::getWeeklyPerformance()` sends `user_id=<id>` in the query string
  and `generateWeeklyTest()` sends `user_id` in the body; both backend handlers
  ignore them entirely and derive the student from the JWT (deliberately, to
  stop id spoofing). `lib/__tests__/api.client.test.ts` asserts these params.
  Harmless dead payload, and removing it is a production change with zero
  security or behaviour benefit — reported, not touched.
- `components/__tests__/TeacherUploadModal.test.tsx` mocks `uploadMaterial` →
  `{quiz_id: 1}` while production returns
  `{message, quiz_id, lesson_id, title, num_questions}`. The component discards
  the response entirely, so this is not behaviour-relevant; left alone rather
  than churned.
- The rest of `lib/__tests__/api.client.test.ts` asserts URL/method/headers/body
  rather than response shapes, and every URL, verb and auth header it asserts
  matches the registered routes. No drift.

### Tests added
- `backend/app/tests/test_answer_redaction.py` (8 new, conventions from
  `test_question_id_wiring.py`, no Gemini/credentials/network): the student
  payload is exactly `{id, question, options, hint}` and the raw body contains
  no `"correct_answer"` at all; an anonymous reader gets the same; the **owning
  teacher** still gets the full six-key legacy shape with the real answer and
  explanation; a *different* teacher gets the sanitized payload; `/check`
  returns the exact feedback body for a right pick, a wrong pick and a
  text-addressed pick; a `question_id` belonging to **another quiz** is rejected
  `404 NOT_FOUND` **and that response body leaks nothing**; `/check` is `401`
  anonymous and `400 VALIDATION_ERROR` with no selection; and `/check` creates
  no `QuizAttempt` while a submit whose client lies about *both* answers still
  scores a server-computed 50%.
- `frontend/app/quiz/[id]/__tests__/page.test.tsx` (3 new): nothing on screen
  reveals the answer before Check and no `/check` request has been made; Check
  posts `{selected_keys:["A"]}` to `/api/quizzes/1/questions/101/check` with the
  bearer token; review-mode explanation and the Incorrect footer render from the
  **server** response; and a failed `/check` still lands on a working Continue
  button.
- Updated in place: `test_legacy_quiz_unification.py` (sanitized default **and**
  a teacher-view assertion, on both the relational and the blob branch),
  `test_personalized_quiz_relational.py` (`LEGACY_QUESTION_KEYS` is now the
  sanitized set — those come from the student-facing generation endpoints),
  `test_question_id_wiring.py` (its legacy-key assertions moved onto
  `to_dict(include_answers=True)`).

### Verification
- `backend/.venv/Scripts/python.exe -m pytest -q` → **83 passed, 0 failed**
  (75 pre-existing + 8 new).
- `cd frontend && npm test` → **12 files, 123 tests passed, 0 failed**
  (120 pre-existing + 3 new).
- `cd frontend && npm run build` → succeeds, same 14 route entries.
- No Alembic migration needed: serialization/read shape only, no schema change.
- `backend/ml/models/*.joblib` churn from the test run reverted; nothing
  committed or pushed; `backend/assesify_dev.db` untouched.

---

## Follow-up session (2026-08-26): authenticated attempt + autosave, `/check` bound to an attempt, Playwright E2E, OTel + Locust

Closes the two items every prior pass carried forward, then picks up the three
testing/observability items that were previously assumed to need absent infra.

### 1. Authenticated attempt + working autosave — `[x]`

**The trap, traced first.** `submitQuiz()` branched on `attemptId`: non-null sent
the quiz to `POST /api/v1/<attempt>/submit` (`attempts_bp`), null sent it to
`POST /api/quizzes/<id>/submit` (`quizzes_bp`). The two are not equivalent:

| | attempts path | legacy path (what production uses) |
|---|---|---|
| score source | recorded `responses` rows only | server-grades the submitted payload from `correct_keys` |
| gamification | none | health, streak, `diamonds_earned` (+5/correct) |
| response body | `{attempt_id, score, correct, total}` | `{message, attempt_id, score, health, streak, diamonds_earned}` |
| mastery | `refresh_student_mastery` | `refresh_student_mastery` |

So simply authenticating attempt-start would have silently moved the score of
record onto a different endpoint and dropped all XP.

**Design chosen — keep the legacy submit as the single score of record, and
have it *reuse* the open attempt.** Least invasive of the three options, and it
avoids inventing a third path:

- `frontend/app/quiz/[id]/page.tsx` — the attempt-start call now sends
  `Authorization: Bearer <token>` (and is skipped entirely when there is no
  token, instead of firing a request that can only 401). `submitQuiz()`'s
  `if (attemptId)` branch is **deleted**: the page always submits through
  `POST /api/quizzes/<id>/submit`, so `attemptId` no longer decides which
  endpoint scores the quiz. `saveResponse()` now sends the bearer token too
  (without it the autosave 401s and no `responses` row is ever written) and
  returns whether the save landed; `handleCheck()` awaits it before asking for
  feedback.
- `backend/app/api/v1/quizzes/routes.py::submit_quiz` — looks for this
  student's open attempt on this quiz (`completed_at IS NULL`) and **reuses**
  it instead of inserting a second `quiz_attempts` row. One quiz-taking session
  is now one attempt row, with the autosaved item-level `responses` attached to
  the attempt that was actually scored. Score, gamification and response body
  are byte-identical to before; a client that never starts an attempt still
  gets a freshly created one, exactly as before.
- Same function now stamps `attempt.completed_at`. It previously left it NULL,
  which meant **every legacy submission was invisible** to
  `refresh_student_mastery`, `get_weekly_performance` and
  `analytics_v1` — all three filter on `completed_at`. That was a live bug, not
  a behaviour change: nothing that used to be counted stops being counted.

New `backend/app/tests/test_attempt_autosave.py` (4): an authenticated
attempt-start followed by an autosave persists a real `responses` row with the
right `question_id`/`selected_keys` and a server-computed `is_correct`;
attempt-start is 401 without a token; the legacy submit reuses the open attempt
(exactly one attempt row, `completed_at` set, both response rows attached) and
still returns `diamonds_earned: 5`, `health: 4`, `streak: 1`; and a submit with
no open attempt still creates one.

`frontend/app/quiz/[id]/__tests__/page.test.tsx` now asserts a
`Bearer test-token` header on **both** the attempt-start and the autosave, the
autosave URL/`question_id`, and that the final submit goes to
`/api/quizzes/1/submit` and **never** to `/42/submit`.

### 2. `/check` bound to the attempt — `[x]` (residual from the previous session closed)

`POST /api/quizzes/<id>/questions/<qid>/check` was an unmetered answer-key
oracle. It now requires an `attempt_id` in the body and enforces, in order:
the attempt exists and belongs to this quiz (404), belongs to the calling
student (403), and **already has a recorded `responses` row for this question**
(409 `ANSWER_REQUIRED`). `is_correct` is now read off that recorded response
rather than re-graded from the request, so feedback and the score of record
cannot disagree.

Revealing is also a **commit**: `responses.revealed_at` is stamped on first
reveal (new nullable column, migration
`a1b2c3d4e5f7_add_revealed_at_to_responses.py`, single head moves from
`f6a7b8c9d0e1`). `POST /api/v1/<attempt>/responses` then refuses to overwrite
that response (`409 ANSWER_LOCKED`), and `submit_quiz` scores a revealed
question from the recorded response rather than the submitted payload. First
selection wins, so harvest-then-resubmit gains nothing. Repeat reveals of an
already-answered question are allowed (idempotent) — they leak nothing new and
back-navigation in the UI needs them.

Frontend: `fetchFeedback()` posts `{attempt_id}` instead of the selection, and
returns the local fallback when there is no attempt. UX unchanged — the
green/red reveal, explanation panel and Continue button all still render from
the server response.

`backend/app/tests/test_answer_redaction.py` grew from 8 to 12 tests, rewritten
onto the new contract: harvesting every question without answering is refused
409 with no leak; legitimate post-answer feedback still returns the exact body;
another student's `attempt_id` is 403; an attempt from a different quiz is 404;
a question id from another quiz is 404; anonymous is 401; missing `attempt_id`
is 400; and the lock test guesses wrong on both questions, harvests both
answers, is refused the overwrite, resubmits with the harvested answers and
still scores **0.0**.

`backend/openapi.yaml`'s `CheckAnswerRequest` now documents `attempt_id` as
required; `npm run gen:types` re-run.

### 3. Playwright E2E — `[x]` (attempted, and it works here)

`@playwright/test@1.62` installed and `npx playwright install chromium`
succeeded — the assumption in every prior entry that no browser runtime was
available was **wrong**.

- `frontend/playwright.config.ts` — two `webServer` entries: the Flask backend
  (`flask run`, port 5101) and a real production Next build (`next build &&
  next start`, port 3101). Both run against a throwaway
  `backend/instance/e2e.db`; `backend/assesify_dev.db` is never touched.
- `backend/e2e_seed.py` — creates the schema, a teacher, a lesson and one quiz
  with relational `Question` rows (the same `persist_quiz_questions()` helper
  the real generator uses), and prints the ids as JSON. Run synchronously while
  the Playwright config is evaluated, so the data exists before either server
  starts.
- `frontend/e2e/quiz-flow.spec.ts` — spec §10's named flow: register → login →
  dashboard → `/quiz/:id` → answer both questions with server feedback →
  "Lesson Complete 2/2" → back to the dashboard with mastery/recommendations
  rendered. It also records every POST the page makes and asserts the
  attempt-start, both autosaves, both `/check` calls and the submit all carried
  an `Authorization` header, and that the submit went to the legacy endpoint —
  i.e. the E2E run independently proves items 1 and 2 in a real browser. A
  second, API-level test asserts the student quiz payload contains no
  `correct_answer`.
- `npm run test:e2e` added, kept **separate** from `npm test`; `e2e/**` is
  excluded from the Vitest include set and from `tsconfig.json` so the unit
  suite stays fast and hermetic, and `next build`'s type pass ignores it.

Two real environment bugs surfaced and were fixed in the harness (not the app):
`NEXT_PUBLIC_*` is inlined at build time and is *not* part of Next's build-cache
key, so a stale `.next` baked in the wrong API base URL (the config now clears
`.next` first); and `app/main.py::add_cors_headers` reflects CORS headers only
for exactly `FRONTEND_URL` (default `http://localhost:3000`), so the E2E backend
is started with `FRONTEND_URL` set to the test frontend origin. Neither is an
application defect — both are correct behaviour that a naive harness trips over.

**Result: `npx playwright test` → 2 passed** against both real servers.

### 4. OpenTelemetry (spec §9) — `[~]`, Locust (spec §10) — `[~]`

**OTel.** `backend/app/core/tracing.py` wires the SDK: a `TracerProvider` with a
`service.name` resource, `FlaskInstrumentor` with a request hook that copies the
existing `X-Request-ID` onto the span as `request.id` (so a trace joins to the
JSON request log), and exporter selection — OTLP/HTTP when
`OTEL_EXPORTER_OTLP_ENDPOINT` is set, `ConsoleSpanExporter` otherwise, or a
caller-supplied exporter. Called from `create_app()` but **opt-in via
`OTEL_ENABLED`**, so the default request path, dev and the existing suite are
untouched. Import failures are swallowed: tracing must never stop the API
booting. `backend/app/tests/test_tracing.py` (2) proves it is off by default and
that a real request produces a span carrying the correlation id, using an
in-memory exporter. `[B]` for the export leg only — no OTLP collector or Grafana
in this environment.

**Locust.** `backend/locustfile.py` defines the 500-concurrent-quiz-taker
scenario: each user registers and logs in with a unique email, then loops the
real student flow (sanitized quiz read → attempt start → per-question autosave →
`/check` → submit), with a lower-weight dashboard analytics task. The exact
`--users 500 --spawn-rate 25` invocation is in its docstring.
`backend/app/tests/test_locustfile.py` (2) imports it and asserts every endpoint
it hits is actually registered on the app's `url_map`, which is where a load
script normally rots. `[B]` for the actual 500-user run — needs a deployment
target, not a dev laptop.

`opentelemetry-{api,sdk,instrumentation-flask,exporter-otlp-proto-http}` and
`locust` added to `backend/requirements.txt` (which is UTF-16 — appended in
that encoding, not clobbered).

### Verification
- `backend/.venv/Scripts/python.exe -m pytest -q` → **95 passed, 0 failed**
  (83 baseline + 4 autosave + 4 net new redaction/lock + 2 tracing + 2 locust).
- `cd frontend && npm test` → **12 files, 123 tests passed, 0 failed**
  (unchanged count; 3 existing quiz-page tests rewritten onto the new contract,
  with added Authorization/endpoint assertions).
- `cd frontend && npx playwright test` → **2 passed**, both servers real.
- `cd frontend && npm run build` → succeeds, same route set.
- Alembic: one new migration, single head is now `a1b2c3d4e5f7`.
- `backend/ml/models/*.joblib` churn from the test run reverted; nothing
  committed or pushed; `backend/assesify_dev.db` untouched.

### Still open
- `[B]` OTLP collector / Grafana dashboards, the real 500-user Locust run, live
  Gemini, live Karmayogi sandbox, real Postgres — all external infrastructure.
- `[ ]` ClamAV upload scanning — spec itself marks it "planned".

## Follow-up session (2026-08-26): environment configuration hardening

An audit of manual/external setup tasks found that `.env` defined 8 variables
while the code reads ~20. Every missing one fell back to an insecure default
*silently* — the app boots and behaves normally, so nothing signals the problem.
Most seriously, `PII_ENCRYPTION_KEY` and `PII_LOOKUP_HASH_SECRET` were absent
from both `.env` and `.env.example`, meaning PII was encrypted under a
publicly-known key committed to this repository.

- `[x]` **`.env.example` completed** — now documents every variable the app
  actually reads (~25), grouped as required-in-production / database / CORS /
  optional Gemini / optional Karmayogi / optional observability / optional Redis,
  with safe placeholders only and no real secrets. Records two footguns found
  during the audit: `DATABASE_URL` driver choice (`postgresql://` vs spec §11.3's
  `postgresql+psycopg://`), and that rotating `PII_LOOKUP_HASH_SECRET` re-keys
  every email lookup hash and locks out all existing users.
- `[x]` **Insecure production defaults now fail fast** — new `APP_ENV` (default
  `development`) and `app/core/config.py::require_secret()`. Under
  `APP_ENV=production`, `SECRET_KEY`, `JWT_SECRET_KEY`, `PII_ENCRYPTION_KEY` and
  `PII_LOOKUP_HASH_SECRET` must each be set, non-empty, and different from their
  documented dev default, or startup raises `InsecureConfigurationError`.
  Outside production the dev defaults are used with a warning, so local dev and
  the test suite need no extra setup. `encrypted_type.py` reuses the same helper
  rather than keeping its own fallback logic.
  Verified manually across all four cases: unset → raises; empty/whitespace →
  raises; value equal to the dev default (i.e. `.env.example` copied verbatim) →
  raises; real secrets → app boots.
- `[x]` **`.env` confirmed untracked** — ignored via `.gitignore:138`; the real
  `.env` was neither read for secrets nor modified.
- `[x]` 8 new tests in `backend/app/tests/test_config_secrets.py` covering the
  dev-fallback, explicit-value, and all four production-rejection paths.

Backend **103 passed, 0 failed** (was 95). `npm run build` succeeds. Nothing
committed.

**Still requires manual action before deployment** (cannot be automated — these
are secrets and infrastructure the operator must supply): generate and set the
four required secrets in the real `.env`, set `APP_ENV=production`,
`NEXT_PUBLIC_API_BASE_URL` and `FRONTEND_URL`, provision PostgreSQL, run
`flask db upgrade head`, and promote a first admin user.

## Follow-up session (2026-08-26): PostgreSQL brought up for real, spec §4.3 attempt routes fixed, production-config guard audited

Three workstreams. The middle one turned out to be a **live production bug**, not
the cosmetic path-naming issue it looked like.

### 1. PostgreSQL — `[x]` (no longer `[B]`)

Every prior entry recorded real Postgres as blocked. It is not any more: the
Docker daemon is up, `postgres:16` pulled (the registry CDN aborts blob
downloads intermittently — it took ~30 retries, nothing repo-related), and
`docker compose up -d postgres` brings the documented stack up on the `.env`
values exactly as written (`DB_PORT=5433`). **No `.env` edit was needed and none
was made**; the file is still gitignored, untracked and unmodified.

- **Migrations reached head.** `FLASK_APP=app.main:app flask db upgrade head`
  against the Postgres `DATABASE_URL` from `.env` ran all 18 revisions in order
  and ended at **`a1b2c3d4e5f7 (head)`**, confirmed with `flask db current`.
- **One real Postgres incompatibility found and fixed.**
  `migrations/versions/f6a7b8c9d0e1_add_oauth_states.py` declared
  `sa.Column('consumed', sa.Boolean(), server_default=sa.text('0'))`. SQLite
  accepts an integer default on a boolean column; PostgreSQL rejects it outright
  ("column ... is of type boolean but default expression is of type integer"),
  so this migration would have failed on every Postgres deployment. Changed to
  `sa.false()`, which renders correctly on both dialects. Verified after the
  upgrade: `information_schema` reports `consumed | boolean | false`.
- **The ORM was exercised, not just the migrations.** A throwaway Flask server
  (port 5055, torn down afterwards; the two dev servers were untouched) was
  pointed at the Postgres URL and driven over real HTTP: register, login,
  `GET /api/quizzes/:id`, start attempt, two autosaved responses, submit, result
  — over both the spec and the legacy attempt paths. **All 10 checks passed.**
  The Postgres-specific things worth watching all behaved:
  - `db.JSON` columns land as native `json` (`questions.options`,
    `questions.correct_keys`, `quizzes.questions`, `responses.selected_keys`) and
    round-trip Python lists correctly through psycopg2.
  - The `EncryptedString` PII columns encrypt/decrypt, and login through the
    deterministic `email_lookup_hash` works — the path most likely to break on a
    dialect change.
  - `b2c3d4e5f6a7`'s backfill was re-read for Postgres safety: it already
    `json.dumps()`es `options`/`correct_keys` before its raw INSERT (a bare
    Python list would be adapted to a PG `ARRAY` and rejected by a `json`
    column) and already handles psycopg2 returning pre-parsed JSON.
- Driver note: `psycopg2` 2.9.12 is what is installed, so `.env`'s plain
  `postgresql://` URL is correct as written. spec §11.3's `postgresql+psycopg://`
  would require the psycopg **3** package, which is not installed — left alone
  deliberately rather than changing a working URL.

### 2. Spec §4.3 attempt routes — a broken user-facing page, now fixed

`attempts_bp` was registered only at `url_prefix="/api/v1"` while its routes are
declared `"/<int:attempt_id>/responses"` etc., so the real paths were
`/api/v1/<id>/result` — **missing the `attempts` segment spec §4.3 requires**.

**This was live breakage, not a naming nit.**
`frontend/app/results/[attemptId]/page.tsx:14` has always fetched
`/api/v1/attempts/${attemptId}/result`. That returned **404**, the page's
`.catch()` swallowed it into `setResult({ feedback: [] })`, and the student
results page rendered an empty score with no feedback, permanently, in
production. Confirmed against the running dev server before the fix (404) and
after (401 — i.e. the route now exists and is asking for auth).

- `app/main.py` now registers **the same blueprint** under both prefixes:
  `/api/v1` (legacy) and `/api/v1/attempts` (spec), the latter via Flask's
  `name="attempts_spec"`. One implementation, two mounts — there is deliberately
  no duplicated route function that could drift.
  `POST /api/v1/quizzes/<quiz_id>/attempts` was already spec-correct and is
  untouched.
- **The legacy paths are preserved.** `frontend/app/quiz/[id]/page.tsx:198` used
  `/api/v1/${attemptId}/responses`; it now uses the spec path, but the old one
  still works for any client that has not moved.
- Frontend updated to the spec paths consistently. `backend/openapi.yaml` already
  documented `/attempts/{attempt_id}/...` — it described the spec rather than the
  code, which is how this slipped through — and one stale prose reference to
  `/api/v1/{attempt_id}/responses` was corrected. `npm run gen:types` re-run.
- New `backend/app/tests/test_attempt_route_aliases.py` (5 tests): the full
  lifecycle over the spec paths; **`GET /api/v1/attempts/<id>/result` returns 200**
  (the explicit regression test for the broken results page); spec and legacy
  paths returning identical JSON for `result` and `next-question`; the
  start-attempt path unchanged; and the alias still enforcing the ownership check
  (403 for another student) — an alias must not become a way around authz.
- **Verified end-to-end in a real browser**, not only by unit test. The Playwright
  suite gained a third test that registers and logs in over HTTP, drives the whole
  attempt through the spec `/attempts/:id/...` paths, asserts
  `GET /api/v1/attempts/:id/result` is 200, then loads `/results/<id>` in Chromium
  and asserts the score and every question's feedback actually render. It fails
  against the old routing.

### 3. Production configuration (spec §8) — verification found two real gaps

`require_secret()` / `APP_ENV` were verified across the full matrix by booting the
app in a fresh subprocess for each case. The guard behaves correctly for the
dev-default and empty-value cases. Two gaps were found and fixed:

- **Gap 1 — the PII secrets were never checked at startup.** `Config` only
  resolves `SECRET_KEY` and `JWT_SECRET_KEY`; `PII_ENCRYPTION_KEY` and
  `PII_LOOKUP_HASH_SECRET` are read lazily by `encrypted_type.py` on the first
  encrypt/decrypt. A production deployment missing them therefore **booted
  cleanly** and only failed later, mid-request, as a 500 — the opposite of
  fail-fast, and easy to miss until a user tried to register. Added
  `config.validate_required_secrets()` (calling a new
  `encrypted_type.get_pii_secrets_for_validation()`), invoked at the top of
  `create_app()`, so all four required secrets resolve before anything is served.
- **Gap 2 — `.env.example`'s placeholders passed the guard.** The check compared
  against the *dev defaults*, but `.env.example` ships
  `SECRET_KEY=replace-me-with-a-generated-secret`. Copying the template verbatim
  and setting `APP_ENV=production` sailed straight through, running production on
  a secret whose value is published in this repository. Added
  `config.PLACEHOLDER_VALUES`, rejected in production alongside the dev defaults.
- Verified matrix (each case boots a fresh interpreter): all four secrets real →
  boots; each one unset, empty, or equal to its dev default → raises
  `InsecureConfigurationError`; `.env.example` placeholders verbatim → raises;
  `APP_ENV=development` with nothing set → boots with warnings. (`SECRET_KEY` /
  `JWT_SECRET_KEY` "unset" only reproduces with `load_dotenv` out of the picture,
  since the developer's real `.env` supplies them; confirmed separately by
  importing `app.core.config` directly, which raises.)
- **`.env.example` audited: safe placeholders only, no real secrets** — and a new
  test asserts that mechanically rather than by eye. It parses the file and fails
  if any `*SECRET*` / `*KEY*` / `*PASSWORD*` / `*TOKEN*` variable holds a value
  that is neither empty nor a known placeholder, and separately that each of the
  four production-required secrets ships a value the guard will actually reject.
  A template that would pass the guard can no longer be committed silently.
- **`.env` confirmed gitignored (`.gitignore:138`), untracked and unmodified**
  (its mtime predates this session). Its values were never printed. `git grep`
  over the tracked tree found no real-looking secret.
- `backend/app/tests/test_config_secrets.py` grew from 8 to 18 tests.

### Verification (final)
- `backend/.venv/Scripts/python.exe -m pytest -q` → **118 passed, 0 failed**
  (103 baseline + 5 attempt-route aliases + 10 config-secret tests).
- `cd frontend && npm test` → **12 files, 123 tests passed, 0 failed** (unchanged
  count; the quiz-page autosave assertion was updated to the spec path).
- `cd frontend && npm run build` → succeeds, same 14 route entries.
- `cd frontend && npx playwright test` → **3 passed** (was 2), real Chromium
  against both real servers; the new one is the results-page regression test.
- Postgres: `flask db upgrade head` → **head `a1b2c3d4e5f7`, no errors**; the
  scripted HTTP flow against Postgres → **10/10 checks passed**.
- `backend/ml/models/*.joblib` churn reverted. Nothing committed or pushed.
- Both dev servers left running: backend `127.0.0.1:5000` (restarted to pick up
  the new route registration, same SQLite `backend/instance/local_verify.db`) and
  frontend `localhost:3000`. The `assesify-postgres` container is left up on 5433.
  `backend/assesify_dev.db` untouched. Note: the Postgres `mydb` database was
  created empty by this session's `docker compose up` and now holds only
  verification data (the `e2e_seed.py` teacher/lesson/quiz plus a couple of
  throwaway test users); drop the `postgres_data` volume if a clean PG is wanted.

### Still requires manual deployment setup (unchanged, cannot be automated)
Generate and set the four required secrets in the real `.env`, set
`APP_ENV=production`, `NEXT_PUBLIC_API_BASE_URL` and `FRONTEND_URL`, point
`DATABASE_URL` at the production Postgres, run `flask db upgrade head`, and
promote a first admin user. Still `[B]`: OTLP collector / Grafana, the real
500-user Locust run, live Gemini, live Karmayogi sandbox.
