# Assesify — Technical Specification (SPEC.md)

> **AI-enabled learning platform** that identifies competency gaps, recommends personalized training through integration with the **iGOT Karmayogi** ecosystem, and generates Quizzes / Multiple Choice Questions (MCQs) from uploaded learning materials to strengthen capacity building.

---

## 1. Overview

**Assesify** is an educational LMS (Learning Management System) that lets teachers deliver quizzes, tracks learner mastery, and produces personalized learning recommendations. It combines:

- A **Next.js** web front end for students and teachers.
- A **Flask** backend API with a **PostgreSQL** datastore for attempts and progress.
- An **ML module** that analyzes quiz results and generates / adapts quizzes (including via **Google Gemini**) to recommend the next topic to study.
- An **integration layer** to the **iGOT Karmayogi** ecosystem for surfacing government-curated courses aligned to identified competency gaps.

### 1.1 Goals
1. Identify **competency gaps** at the learner and cohort level.
2. Recommend **personalized training** paths, including Karmayogi courses.
3. Generate **Quizzes & MCQs** automatically from uploaded materials (PDF, DOCX, TXT, slides).
4. Provide teachers with **analytics** on mastery and misconceptions.
5. Support **capacity building** at scale for public-sector and enterprise learners.

### 1.2 Non-Goals
- Not a full replacement for iGOT Karmayogi — Assesify augments it.
- No live proctoring in v1 (planned for v2).
- No native mobile apps in v1; the web app is responsive.

---

## 2. Architecture

### 2.1 High-Level Diagram

```
 ┌──────────────────┐      HTTPS/JSON       ┌────────────────────────┐
 │  Next.js (TS)    │  ───────────────────▶ │   Flask API (Python)   │
 │  Web Front End   │  ◀─────────────────── │   REST + JWT Auth      │
 └────────┬─────────┘                        └──────┬─────────────────┘
          │                                         │
          │ (auth, uploads, quiz UI)                │
          │                                         ▼
          │                              ┌────────────────────────┐
          │                              │  ML Module (Python)    │
          │                              │  scikit-learn + Gemini │
          │                              └──────┬─────────────────┘
          │                                     │
          │                                     ▼
          │                              ┌────────────────────────┐
          │                              │  PostgreSQL (Docker)   │
          │                              └────────────────────────┘
          │                                     │
          │                                     ▼
          │                              ┌────────────────────────┐
          └─────────────────────────────▶│  iGOT Karmayogi API    │
                                         │  (Course Recommender)  │
                                         └────────────────────────┘
```

### 2.2 Components

| Component | Tech | Responsibility |
|---|---|---|
| **Web Frontend** | Next.js 14 (App Router), TypeScript, TailwindCSS | Auth UI, quiz-taking, teacher dashboards, uploads |
| **Backend API** | Flask 3.x (Python 3.11+), Flask-JWT-Extended, SQLAlchemy | REST endpoints, auth, orchestration |
| **ML Module** | Python, scikit-learn, NumPy, pandas, google-generativeai (Gemini) | Question generation, gap analysis, recommendations |
| **Database** | PostgreSQL 16 (Docker Compose) | Users, quizzes, attempts, progress, embeddings |
| **Object Storage** | Local FS (v1) / S3-compatible (v2) | Uploaded materials |
| **Karmayogi Connector** | Python module + REST client | Fetches / maps competency → courses |

### 2.3 Deployment
- `docker-compose.yml` orchestrates: `frontend`, `backend`, `postgres`, `ml-worker`.
- Environments: `dev`, `staging`, `prod` via `.env` files.
- CI/CD: GitHub Actions → build images → deploy.

---

## 3. Data Model (PostgreSQL)

### 3.1 Core Tables

```sql
-- Users (students, teachers, admins)
users (
  id UUID PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  full_name TEXT,
  role TEXT CHECK (role IN ('student','teacher','admin')),
  karmayogi_user_id TEXT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Learning materials uploaded by teachers
materials (
  id UUID PRIMARY KEY,
  owner_id UUID REFERENCES users(id),
  title TEXT,
  file_path TEXT,
  mime_type TEXT,
  extracted_text TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Quizzes (human-authored or AI-generated)
quizzes (
  id UUID PRIMARY KEY,
  material_id UUID REFERENCES materials(id) NULL,
  owner_id UUID REFERENCES users(id),
  title TEXT,
  competency_tags TEXT[],
  generated_by TEXT CHECK (generated_by IN ('human','gemini','hybrid')),
  created_at TIMESTAMPTZ DEFAULT now()
);

questions (
  id UUID PRIMARY KEY,
  quiz_id UUID REFERENCES quizzes(id) ON DELETE CASCADE,
  stem TEXT NOT NULL,
  qtype TEXT CHECK (qtype IN ('mcq','msq','short','tf')),
  options JSONB,          -- [{"key":"A","text":"..."}]
  correct_keys TEXT[],
  difficulty NUMERIC(3,2),
  competency_tag TEXT
);

attempts (
  id UUID PRIMARY KEY,
  student_id UUID REFERENCES users(id),
  quiz_id UUID REFERENCES quizzes(id),
  started_at TIMESTAMPTZ,
  submitted_at TIMESTAMPTZ,
  score NUMERIC(5,2)
);

responses (
  id UUID PRIMARY KEY,
  attempt_id UUID REFERENCES attempts(id) ON DELETE CASCADE,
  question_id UUID REFERENCES questions(id),
  selected_keys TEXT[],
  is_correct BOOLEAN,
  time_ms INTEGER
);

-- Per-learner competency mastery snapshots
competency_mastery (
  id UUID PRIMARY KEY,
  student_id UUID REFERENCES users(id),
  competency_tag TEXT,
  mastery NUMERIC(3,2),   -- 0.00 - 1.00
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (student_id, competency_tag)
);

-- Karmayogi course recommendations
recommendations (
  id UUID PRIMARY KEY,
  student_id UUID REFERENCES users(id),
  competency_tag TEXT,
  karmayogi_course_id TEXT,
  score NUMERIC(4,3),
  reason TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### 3.2 Indexes
- `attempts(student_id, submitted_at DESC)`
- `responses(attempt_id)`
- `competency_mastery(student_id)`
- GIN index on `quizzes.competency_tags`.

---

## 4. Backend API (Flask)

Base URL: `/api/v1`. All non-auth endpoints require `Authorization: Bearer <JWT>`.

### 4.1 Auth

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Register student/teacher |
| POST | `/auth/login` | Returns JWT (access + refresh) |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/karmayogi/link` | Link Karmayogi identity |

### 4.2 Materials & Generation

| Method | Path | Description |
|---|---|---|
| POST | `/materials` | Upload a PDF/DOCX/TXT; server extracts text |
| GET  | `/materials/:id` | Metadata + extracted text |
| POST | `/materials/:id/generate-quiz` | Trigger Gemini-based quiz generation |

**Generation request body:**
```json
{
  "num_questions": 10,
  "difficulty": "mixed",
  "qtypes": ["mcq","msq","tf"],
  "competency_tags": ["policy-analysis","budgeting"]
}
```

### 4.3 Quizzes & Attempts

| Method | Path | Description |
|---|---|---|
| GET  | `/quizzes` | List quizzes for current user |
| GET  | `/quizzes/:id` | Full quiz (teacher view) or sanitized (student) |
| POST | `/quizzes/:id/attempts` | Start attempt |
| POST | `/attempts/:id/responses` | Submit response to a question |
| POST | `/attempts/:id/submit` | Finalize attempt, score, update mastery |
| GET  | `/attempts/:id/result` | Detailed feedback |

### 4.4 Analytics & Recommendations

| Method | Path | Description |
|---|---|---|
| GET | `/students/:id/mastery` | Competency mastery vector |
| GET | `/students/:id/gaps` | Ranked list of competency gaps |
| GET | `/students/:id/recommendations` | Karmayogi + internal course recs |
| GET | `/teachers/cohorts/:id/analytics` | Class-level dashboards |

### 4.5 Error Format
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "...", "details": {} } }
```

---

## 5. ML Module

### 5.1 Question Generation (Gemini)

**Pipeline:**
1. `extract_text(material)` — PyMuPDF / python-docx.
2. `chunk_text(text, size=1200, overlap=150)` — semantic chunks.
3. `tag_competencies(chunk)` — zero-shot classifier over configured taxonomy (e.g., Karmayogi competency framework).
4. `gemini_generate(chunk, spec)` — structured prompt returning strict JSON:
   ```json
   {
     "questions": [
       {
         "stem": "...",
         "qtype": "mcq",
         "options": [{"key":"A","text":"..."}, ...],
         "correct_keys": ["B"],
         "explanation": "...",
         "difficulty": 0.55,
         "competency_tag": "policy-analysis"
       }
     ]
   }
   ```
5. `validate_and_dedupe()` — schema check, near-duplicate removal via embedding cosine ≥ 0.92.
6. `persist()` — write to `questions` table.

**Prompt contract:** the Gemini prompt is versioned in `ml/prompts/generate_mcq_v1.txt` and is enforced with a JSON schema; malformed outputs are retried up to 2 times before fallback to a rule-based generator.

### 5.2 Competency Gap Analysis (scikit-learn)

For each `student_id`:
- Build response matrix `X ∈ R^{n_questions × n_features}` — features: `is_correct`, `time_ms_z`, `difficulty`, `competency_tag_onehot`.
- Update per-competency mastery with a **logistic-regression IRT-style estimator**:
  - `mastery[c] = sigmoid(θ_c)` where `θ_c` is fit with L2 regularization on the student's recent (last 90 days) responses in competency `c`.
- Persist to `competency_mastery`.
- **Gaps** = competencies with `mastery < 0.6`, ranked by `(0.6 - mastery) * weight_c`.

### 5.3 Recommendation
For each gap `c`:
1. Query Karmayogi catalog for courses tagged `c`.
2. Score each course:
   `score = w1 * tag_overlap + w2 * difficulty_match + w3 * recency + w4 * rating`.
3. Return top-K per gap; also return internal remedial quizzes.

### 5.4 Adaptive Quiz Selection
- If teacher enables "adaptive mode", the next question is selected by maximizing expected information gain about the student's weakest competency (Bayesian update of `θ_c`).

---

## 6. iGOT Karmayogi Integration

### 6.1 Capabilities Used
- **Identity link**: map `users.karmayogi_user_id` via OAuth2 (client-credentials for server-to-server; PKCE for user-consented flows).
- **Course catalog**: `GET /karmayogi/api/course/v1/list?competency=<tag>`.
- **Progress push**: `POST /karmayogi/api/progress/v1/update` — sync Assesify mastery events so Karmayogi can reflect learner growth.
- **Competency framework**: pull the canonical competency taxonomy at boot; cache 24h.

### 6.2 Connector Module

```
ml/integrations/karmayogi/
  client.py         # Async httpx client with retry + circuit breaker
  mapping.py        # competency_tag <-> karmayogi_competency_id
  recommender.py    # gap -> ranked courses
  sync.py           # push mastery/attempt events
```

### 6.3 Configuration
```
KARMAYOGI_BASE_URL=
KARMAYOGI_CLIENT_ID=
KARMAYOGI_CLIENT_SECRET=
KARMAYOGI_COMPETENCY_CACHE_TTL=86400
```

### 6.4 Fallback
If Karmayogi is unavailable, the recommender degrades to **internal remedial quizzes** and surfaces a banner in the UI.

---

## 7. Frontend (Next.js)

### 7.1 Routes

| Route | Role | Purpose |
|---|---|---|
| `/login`, `/register` | public | Auth |
| `/dashboard` | student | Mastery radar + recommended courses |
| `/quiz/[id]` | student | Take quiz (adaptive-aware) |
| `/results/[attemptId]` | student | Feedback + next-topic recs |
| `/teacher` | teacher | Cohorts, upload materials |
| `/teacher/materials/[id]` | teacher | Generate quiz from material |
| `/teacher/quizzes/[id]/analytics` | teacher | Item analysis, misconception heat map |

### 7.2 Key UX
- **Quiz UI**: single-question view, keyboard nav, autosave every response.
- **Mastery radar**: competency vector visualization (Recharts / D3).
- **Recommendation cards**: Karmayogi course cards with "Enroll on Karmayogi" deep link.
- **Teacher upload**: drag-and-drop; on completion, a "Generate MCQs" CTA opens a config drawer (count, difficulty, types, competencies).

### 7.3 State & Data
- **State**: React Server Components + `@tanstack/react-query` for client caches.
- **Auth**: JWT in httpOnly cookie; refresh via `/auth/refresh` middleware.
- **Types**: shared OpenAPI schema → generated TS types (`openapi-typescript`).

---

## 8. Security & Compliance

- **AuthN**: JWT (HS256 dev / RS256 prod), refresh tokens rotated.
- **AuthZ**: Role-based (`student`, `teacher`, `admin`) + ownership checks per resource.
- **Passwords**: `argon2id` via `argon2-cffi`.
- **PII**: Encrypt `email`, `full_name` at rest with pgcrypto; audit log for admin access.
- **Uploads**: MIME sniffing + size cap (25 MB v1); virus scan hook (ClamAV) planned.
- **Rate limiting**: Flask-Limiter, 60 req/min per IP on auth endpoints.
- **CORS**: strict allowlist for frontend origin.
- **Secrets**: `.env` in dev; managed secret store (e.g., AWS SM / Vault) in prod.
- **Data residency**: PostgreSQL region configurable; Karmayogi calls stay within India region.

---

## 9. Observability

- **Logging**: structured JSON via `structlog`; correlation IDs propagated `X-Request-ID`.
- **Metrics**: Prometheus (`/metrics`) — request latency, quiz gen duration, Gemini token usage.
- **Tracing**: OpenTelemetry → OTLP collector.
- **Dashboards**: Grafana (latency, error rate, generation success ratio).

---

## 10. Testing Strategy

| Layer | Tooling | Coverage target |
|---|---|---|
| Backend unit | `pytest`, `pytest-asyncio` | ≥ 85 % on services & ML utils |
| Backend integration | `pytest` + testcontainers Postgres | Critical flows |
| ML | Golden-set MCQs; JSON-schema validation; embedding-dedup tests | 100 % of generation contracts |
| Frontend unit | Vitest + React Testing Library | ≥ 75 % |
| E2E | Playwright | Auth, upload → generate → attempt → recs |
| Load | Locust | 500 concurrent quiz takers |

---

## 11. Local Development

### 11.1 Prerequisites
- Node.js 20+, pnpm 9+
- Python 3.11+, `uv` or `poetry`
- Docker Desktop / Colima

### 11.2 Bootstrap

```bash
git clone <repo> assesify && cd assesify
cp .env.example .env         # fill Gemini + Karmayogi keys
docker compose up -d postgres
# Backend
cd backend && uv sync && uv run flask db upgrade && uv run flask run
# Frontend
cd ../frontend && pnpm i && pnpm dev
```

### 11.3 Env Vars

```
# Backend
DATABASE_URL=postgresql+psycopg://assesify:assesify@localhost:5432/assesify
JWT_SECRET=change-me
GEMINI_API_KEY=
KARMAYOGI_BASE_URL=
KARMAYOGI_CLIENT_ID=
KARMAYOGI_CLIENT_SECRET=

# Frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:5000/api/v1
```

### 11.4 docker-compose.yml (excerpt)

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: assesify
      POSTGRES_PASSWORD: assesify
      POSTGRES_DB: assesify
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  backend:
    build: ./backend
    env_file: .env
    depends_on: [postgres]
    ports: ["5000:5000"]
  frontend:
    build: ./frontend
    env_file: .env
    depends_on: [backend]
    ports: ["3000:3000"]
volumes: { pgdata: {} }
```

---

## 12. Repository Layout

```
assesify/
├── frontend/                 # Next.js + TS
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── package.json
├── backend/                  # Flask + Python
│   ├── app/
│   │   ├── api/              # blueprints per resource
│   │   ├── models/           # SQLAlchemy
│   │   ├── services/         # business logic
│   │   └── extensions.py
│   ├── ml/
│   │   ├── generation/       # Gemini pipeline
│   │   ├── mastery/          # scikit-learn IRT
│   │   ├── recommender/
│   │   ├── integrations/karmayogi/
│   │   └── prompts/
│   ├── migrations/           # Alembic
│   └── pyproject.toml
├── docker-compose.yml
├── .env.example
└── SPEC.md
```

---

## 13. Milestones

| # | Milestone | Deliverables |
|---|---|---|
| M1 | Foundations | Auth, users, docker-compose, CI |
| M2 | Materials + MCQ generation | Upload, Gemini pipeline, teacher review UI |
| M3 | Quizzing + attempts | Student flow, scoring, feedback |
| M4 | Mastery + gap analysis | scikit-learn IRT, mastery radar |
| M5 | Karmayogi integration | OAuth link, catalog, recommendations |
| M6 | Adaptive quizzing | Bayesian item selection |
| M7 | Analytics & hardening | Teacher analytics, load tests, security review |

---

## 14. Open Questions

1. Final Karmayogi API contract & sandbox credentials for progress-push.
2. Canonical competency taxonomy source of truth (Karmayogi vs. internal).
3. Data-retention policy for uploaded materials containing sensitive content.
4. Multilingual generation scope for v1 (English + Hindi baseline?).
5. Accessibility: WCAG 2.1 AA is target — audit tooling to be selected.

---

## 15. Glossary

- **Competency**: A named skill/knowledge area (e.g., `budgeting`, `policy-analysis`).
- **Mastery**: Estimated probability the learner answers a target-difficulty question in a competency correctly (0–1).
- **Gap**: Competency where mastery is below the configured threshold (default `0.6`).
- **iGOT Karmayogi**: The Government of India's integrated online training platform for civil servants.

---

*End of SPEC.md*

---

## 16. Implementation Status

Audit scope: current repository state, including the versioned API additions. Statuses describe the implemented behavior, not planned or documented behavior.

| Major requirement | Status | Evidence / notes |
|---|---|---|
| Next.js + TypeScript learning UI | Partially Completed | Student, teacher, class, quiz, analytics, and profile screens exist under `frontend/app/`; the app uses Next.js 16 rather than the specified Next.js 14. |
| Flask + SQLAlchemy backend | Completed | Application factory and blueprints: `backend/app/main.py`, `backend/app/models/`, `backend/app/api/v1/`. |
| PostgreSQL local datastore | Partially Completed | SQLAlchemy models and Alembic migrations exist; `docker-compose.yml` provisions PostgreSQL 15 only, rather than the specified PostgreSQL 16 full stack. |
| Full Docker deployment stack (frontend, backend, PostgreSQL, ML worker) | Partially Completed | `docker-compose.yml`, `backend/Dockerfile`, and `frontend/Dockerfile` define frontend, backend, PostgreSQL 16, Redis, and an ML worker; image/runtime integration has not been exercised against real credentials. |
| Environment separation and CI/CD | Not Implemented | No environment-specific configuration set or GitHub Actions workflow is present. |

### Data model and API

| Major requirement | Status | Evidence / notes |
|---|---|---|
| Users with student/teacher/admin roles and Karmayogi identity | Partially Completed | `backend/app/models/users.py` has a teacher boolean and `karmayogi_user_id`; UUIDs, an admin role, and the specified role constraint are absent. |
| Materials, normalized quizzes/questions/responses, and required indexes | Partially Completed | Lessons, JSON-backed quizzes, attempts, answers, mastery, and recommendations exist in `backend/app/models/`; materials/questions/responses are not normalized as specified and most specified indexes are absent. |
| Versioned `/api/v1` API | Partially Completed | Versioned blueprints are registered in `backend/app/main.py`, but several specified resources use only legacy route shapes or are missing. |
| Registration, login, refresh, and identity linking | Partially Completed | `backend/app/api/v1/auth/routes.py` supports these operations, but refresh-token rotation, cookie storage, OAuth2/PKCE, and complete validation are absent. |
| Material upload, text extraction, and quiz generation API | Partially Completed | `backend/app/api/v1/teacher/routes.py` handles PDF/DOCX/TXT upload, extraction, and generation; it does not expose the specified `/materials/:id` resource contract or slide support. |
| Quiz listing, sanitized delivery, attempt lifecycle, per-response autosave, and results API | Partially Completed | `backend/app/api/v1/attempts/routes.py` and `backend/app/models/assessment.py` provide start/respond/finalize/result flow for normalized v1 quizzes; legacy JSON quizzes still use the original one-shot route. |
| Learner mastery, gaps, and recommendations APIs | Partially Completed | `backend/app/api/v1/students/routes.py` and `backend/app/services/mastery_service.py` implement these endpoints; cohort analytics uses a different, less specific route in `backend/app/api/v1/teacher/routes.py`. |
| Standard API error envelope | Partially Completed | A few new routes return the specified envelope; legacy routes generally return `msg` or ad-hoc error payloads. |

### ML, recommendations, and Karmayogi

| Major requirement | Status | Evidence / notes |
|---|---|---|
| Gemini-backed MCQ generation with fallback | Partially Completed | Gemini wrapper and rule-based fallback exist in `backend/ml/genai.py` and `backend/ml/train/quiz_gen.py`; question types and output contract are simpler than specified. |
| Semantic chunking, competency taxonomy tagging, schema retries, and embedding deduplication | Not Implemented | `chunk_text` is fixed-word chunking; no taxonomy classifier, versioned prompt file, retry policy, or embedding deduplication is present. |
| Persisted, item-level validated questions | Partially Completed | Generated questions are persisted inside `Quiz.questions` JSON in `backend/app/models/quiz.py`, not in the specified `questions` table. |
| 90-day logistic/IRT competency estimator | Partially Completed | `backend/app/services/mastery_service.py` computes a recent weighted accuracy estimate and persists snapshots; it is not the specified logistic-regression IRT estimator and has no response timing feature. |
| Gap ranking at mastery threshold | Partially Completed | `backend/app/services/mastery_service.py` applies the `0.6` threshold; competency weighting is not implemented. |
| Personalized and remedial recommendations | Partially Completed | Rule-based personalized generation is in `backend/ml/recommender.py`; gap recommendations and internal fallback are in `backend/app/services/karmayogi_service.py`. The specified multi-factor course scoring is absent. |
| Adaptive question selection | Partially Completed | `backend/ml/adaptive.py` and `backend/app/api/v1/attempts/routes.py` select an unanswered question using logistic item information near current mastery; teacher mode configuration and a full Bayesian posterior are absent. |
| Karmayogi course-catalog integration and fallback | Partially Completed | `backend/app/services/karmayogi_service.py` calls the configured catalog endpoint and falls back to internal practice; no async client, retry/circuit breaker, competency mapping, or UI availability banner exists. |
| Karmayogi OAuth, taxonomy cache, and progress push | Not Implemented | Only direct ID linking is implemented; no OAuth flow, taxonomy synchronization/cache, or progress-update call exists. |

### Frontend, security, operations, and quality

| Major requirement | Status | Evidence / notes |
|---|---|---|
| Required public/student/teacher route set | Partially Completed | `/login`, `/register`, `/dashboard`, `/quiz/[id]`, and `/teacher` exist; `/results/[attemptId]`, teacher material detail, and quiz analytics detail routes are absent. |
| Quiz UX: single question, keyboard navigation, autosave, adaptive awareness | Partially Completed | `frontend/app/quiz/[id]/page.tsx` provides a question-taking screen; keyboard navigation, response autosave, and adaptive delivery are absent. |
| Mastery radar and Karmayogi recommendation cards | Partially Completed | `frontend/components/MasteryRecommendations.tsx` renders mastery bars and recommendation/deep links; it is not yet a Recharts/D3 radar visualization. |
| Teacher drag/drop upload and generation configuration | Partially Completed | `frontend/components/TeacherUploadModal.tsx` supports drag/drop, count, and difficulty; question-type and competency controls plus post-generation review are absent. |
| React Query, httpOnly-cookie auth, and generated OpenAPI types | Not Implemented | `frontend/lib/api.ts` uses direct `fetch` and localStorage; no React Query or OpenAPI type generation is present. |
| JWT authentication and basic authorization | Partially Completed | JWT guards appear on selected routes; authorization is inconsistent, legacy endpoints accept caller-supplied user IDs, and there is no admin role. |
| Password, PII, upload, rate-limit, and CORS controls | Partially Completed | Passwords use Werkzeug hashing and uploads enforce extension/25 MB limits; Argon2id, PII encryption/audit logs, MIME sniffing, virus hooks, Flask-Limiter, and a production CORS policy are absent or incomplete. |
| Secrets and data residency controls | Partially Completed | Environment variables are read in `backend/app/core/config.py`; managed secrets, region enforcement, and India-only integration controls are absent. |
| Structured logs, metrics, tracing, and dashboards | Partially Completed | `backend/app/main.py` adds JSON request logs, correlation IDs, and a Prometheus-compatible `/metrics` response; structlog, OpenTelemetry, and Grafana are still absent. |
| Automated test strategy and coverage targets | Partially Completed | Backend/ML pytest-style tests exist in `backend/ml/tests/`; frontend unit tests, E2E, load tests, testcontainers, and stated coverage enforcement are absent. |
| Local-development documentation and bootstrap | Partially Completed | `README.md` documents setup, but it does not match the current package tooling and the compose stack is incomplete. |

### Milestone summary

| Milestone | Status | Basis |
|---|---|---|
| M1 — Foundations | Partially Completed | Basic auth, users, migrations, and database container exist; CI and complete RBAC/security do not. |
| M2 — Materials + MCQ generation | Partially Completed | Upload/extraction and basic Gemini generation exist; review workflow and generation contract do not. |
| M3 — Quizzing + attempts | Partially Completed | Quiz UI, scoring, and attempts exist; the specified attempt lifecycle and feedback route do not. |
| M4 — Mastery + gap analysis | Partially Completed | Persisted mastery and gaps exist; IRT and mastery radar do not. |
| M5 — Karmayogi integration | Partially Completed | Catalog attempt/fallback and identity field exist; OAuth, mapping, cache, and progress push do not. |
| M6 — Adaptive quizzing | Partially Completed | Normalized attempts can request an information-based next question; teacher enablement and full Bayesian estimation are still pending. |
| M7 — Analytics + hardening | Partially Completed | Basic teacher analytics exists; observability, load tests, and security review controls do not. |
