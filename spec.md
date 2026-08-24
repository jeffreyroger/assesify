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

