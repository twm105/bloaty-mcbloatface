# Architecture Guide

Internal system architecture for Bloaty McBloatface. For deployment details see [DEVOPS.md](DEVOPS.md), for security patterns see [SECURITY.md](SECURITY.md).

---

## 1. System Overview

```
                    ┌──────────┐
                    │  Client  │
                    │ (Browser)│
                    └────┬─────┘
                         │ HTTP / SSE
                    ┌────▼─────┐
                    │  nginx   │  Static files, reverse proxy
                    │  :80     │
                    └────┬─────┘
                         │
                    ┌────▼─────┐         ┌───────────┐
                    │   web    │────────▶│    db     │
                    │ FastAPI  │         │ PostgreSQL│
                    │  :8000   │         │   :5432   │
                    └────┬─────┘         └───────────┘
                         │
                    ┌────▼─────┐
                    │  redis   │◀──────── worker
                    │  :6379   │         (Dramatiq)
                    └──────────┘
```

**Five containers** orchestrated via Docker Compose:

| Container | Image | Role |
|-----------|-------|------|
| **db** | postgres:16-alpine | Primary data store |
| **redis** | redis:7-alpine | Message broker + pub/sub for SSE |
| **web** | Custom (Dockerfile) | FastAPI application server |
| **worker** | Same image as web | Dramatiq background task processor |
| **nginx** | nginx:alpine | Reverse proxy, static file serving |

Startup order enforced via health checks: db/redis must be healthy before web starts, web must be healthy before nginx starts. Worker depends on db and redis.

---

## 2. Application Layers

```
Routes (app/api/)
  │  HTTP handlers, request validation, HTML responses
  ▼
Services (app/services/)
  │  Business logic, AI integration, orchestration
  ▼
Models (app/models/)
  │  SQLAlchemy ORM, schema definitions
  ▼
Database (PostgreSQL)
```

### Routes (`app/api/`)

Seven router modules mounted on the FastAPI app:

| Router | Prefix | Responsibility |
|--------|--------|----------------|
| `auth.py` | `/auth` | Login, registration, account management |
| `routes.py` | `/` | Home, analysis dashboard, settings pages |
| `meals.py` | `/meals` | Meal CRUD, ingredient editing, image upload |
| `symptoms.py` | `/symptoms` | Symptom logging, AI elaboration, history |
| `diagnosis.py` | `/diagnosis` | Trigger analysis, feedback, result views |
| `diagnosis_sse.py` | `/diagnosis` | SSE streaming for real-time diagnosis progress |
| `feedback.py` | `/feedback` | User feedback submission |

### Services (`app/services/`)

| Service | Key Class | Responsibility |
|---------|-----------|----------------|
| `ai_service.py` | `ClaudeService` | All Claude API interactions (analysis, clarification, diagnosis) |
| `ai_schemas.py` | Pydantic models | Structured output validation for AI responses |
| `prompts.py` | Constants | System prompts for all AI capabilities |
| `ai_usage_service.py` | `AIUsageService` | API cost tracking and analytics |
| `meal_service.py` | `MealService` | Meal CRUD, ingredient management, copy/publish |
| `symptom_service.py` | `SymptomService` | Symptom CRUD, episode detection, tag management |
| `diagnosis_service.py` | `DiagnosisService` | Temporal correlation analysis, data sufficiency checks |
| `diagnosis_queue_service.py` | `DiagnosisQueueService` | Enqueue Dramatiq tasks for async diagnosis |
| `sse_publisher.py` | `SSEPublisher` / `SSESubscriber` | Redis pub/sub for real-time progress events |
| `file_service.py` | `FileService` | Image upload, optimization, EXIF rotation |
| `auth/` | `AuthProvider` | Pluggable authentication (strategy pattern) |

### Models (`app/models/`)

18 SQLAlchemy models — see [Section 6](#6-database-relationships) for the full relationship diagram.

### Workers (`app/workers/`)

| Actor | File | Role |
|-------|------|------|
| `analyze_ingredient` | `diagnosis_worker.py` | Per-ingredient AI analysis pipeline |
| `finalize_diagnosis_run` | `diagnosis_worker.py` | Mark run complete, publish final SSE event |

Run command: `dramatiq app.workers.diagnosis_worker --processes 1 --threads 4`

### Templates (`app/templates/`)

Jinja2 templates with htmx for dynamic updates and Alpine.js for reactive state:

```
templates/
├── base.html                  # Master layout (nav, scripts, styles)
├── home.html, analysis.html, settings.html
├── auth/                      # login, register, account
├── meals/
│   ├── log.html, edit_ingredients.html, history.html
│   ├── _meal_card.html        # Reusable card component
│   └── partials/              # htmx swap targets
├── symptoms/                  # log, history, edit
├── diagnosis/                 # Results views
└── components/                # Shared UI components
```

---

## 3. Request Lifecycle

### Example: Logging a Meal

```
1. User uploads image + notes
   POST /meals/create (multipart form)
        │
2. Route handler (meals.py)
   ├── Auth: get_current_user() extracts user from session cookie
   ├── FileService.save_meal_image() → optimize, save to /uploads/
   ├── MealService.create_meal() → INSERT Meal (status=draft)
   └── ClaudeService.analyze_meal_image() → Claude API call
        │
3. AI returns structured ingredients (validated against MealAnalysisSchema)
   ├── MealService.update_meal_ingredients() → INSERT MealIngredients
   └── Return HTML partial (htmx fragment)
        │
4. htmx swaps ingredient list into DOM
   User edits ingredients (add/remove/modify state)
        │
5. POST /meals/{id}/publish → MealService.publish_meal()
   Meal status: draft → published
```

### htmx Partial Pattern

Routes return HTML fragments (not full pages) for htmx requests:

```python
# Route returns a partial template
return templates.TemplateResponse("meals/partials/ingredient_item.html", {...})

# htmx swaps it into the target element
# <button hx-post="/meals/1/publish" hx-target="#meal-status" hx-swap="outerHTML">
```

### Auth Dependency Injection

```python
# Session cookie → database lookup → User object
@router.post("/meals/create")
async def create_meal(user: User = Depends(get_current_user), ...):
    # user is guaranteed authenticated here

# Page-level auth (redirects to /auth/login instead of 401)
@router.get("/meals/history")
async def meal_history(user: User = Depends(RequireAuthPage()), ...):
```

---

## 4. AI Integration Architecture

### Three AI Capabilities

| Capability | Service Method | Model | Features |
|-----------|---------------|-------|----------|
| Meal image analysis | `analyze_meal_image()` | Sonnet | Image input, ingredient detection |
| Symptom clarification | `clarify_symptom()`, `elaborate_on_symptom()` | Sonnet | Conversational Q&A, episode detection |
| Diagnosis correlation | `research_ingredient()`, `classify_root_cause()`, `adapt_to_plain_english()` | Sonnet | Web search, prompt caching |

### Structured Output Pipeline

```
Claude API response (raw JSON string)
  │
  ├── Strip markdown fences (_strip_markdown_json)
  ├── Fix trailing commas (_fix_trailing_commas)
  │
  ▼
Pydantic schema validation (e.g., MealAnalysisSchema)
  │
  ├── Success → return validated object
  └── Failure → retry with schema error feedback (_call_with_schema_retry)
```

Key schemas in `ai_schemas.py`:
- `MealAnalysisSchema` — meal name + ingredients array
- `ClarifySymptomSchema` — discriminated union (question mode vs complete mode)
- `SingleIngredientDiagnosisSchema` — per-ingredient diagnosis + recommendations
- `ResearchIngredientSchema` — medical assessment + trigger categories + risk level
- `RootCauseSchema` — boolean classification with justification
- `CitationSchema` — medical citations with URL, title, type, snippet

### Prompt Management (`prompts.py`)

System prompts defined as constants with medical ethics compliance built in. Key prompts:
- `MEAL_ANALYSIS_SYSTEM_PROMPT` — v3 recipe inference
- `SYMPTOM_CLARIFICATION_SYSTEM_PROMPT` — max 3 clarifying questions
- `DIAGNOSIS_SINGLE_INGREDIENT_PROMPT` — per-ingredient analysis
- `RESEARCH_INGREDIENT_PROMPT` — medical research with web search
- `build_cached_analysis_context()` — prompt caching for diagnosis cost reduction

### Error Handling

| Error | Trigger | Handling |
|-------|---------|----------|
| `ServiceUnavailableError` | API down after retries | User-facing error message |
| `RateLimitError` | Rate limit exceeded | Backoff, user notification |
| `SchemaValidationError` | Response doesn't match schema | Retry with error context |
| Connection errors | Network issues | `retry_on_connection_error()` decorator, exponential backoff with jitter |

### Cost Tracking (`ai_usage_service.py`)

Every API call logged to `AIUsageLog` with model, token counts, and estimated cost. Cached tokens charged at 10% of normal rate. Costs aggregated per diagnosis run via `(request_id, request_type)` linking.

For AI quality measurement, see [EVALS_STRATEGY.md](EVALS_STRATEGY.md).

---

## 5. Async Processing Pipeline (Diagnosis)

### Overview

Diagnosis runs asynchronously to handle multiple AI calls per ingredient without blocking the HTTP request. Uses Dramatiq (Redis broker) for task distribution and Redis pub/sub for real-time progress.

### Flow

```
Client                    Web Server              Worker              Redis
  │                          │                      │                   │
  ├─POST /diagnosis/analyze──▶                      │                   │
  │                          ├─ DiagnosisService:    │                   │
  │                          │  prepare correlation  │                   │
  │                          │  data (SQL)           │                   │
  │                          │                       │                   │
  │                          ├─ DiagnosisQueueService:                   │
  │                          │  enqueue tasks ───────────────────────────▶ (message queue)
  │                          │                       │                   │
  │                          ◀─ Return run_id ───────│                   │
  │◀── 200 {run_id} ────────┤                       │                   │
  │                          │                       │                   │
  ├─GET /diagnosis/stream/{run_id}──▶                │                   │
  │  (SSE connection)        ├──SSESubscriber────────│───────────────────▶ (pub/sub subscribe)
  │                          │                       │                   │
  │                          │              ┌────────┤                   │
  │                          │              │ analyze_ingredient()       │
  │                          │              │  1. research_ingredient()  │
  │                          │              │  2. classify_root_cause()  │
  │                          │              │  3. adapt_to_plain_english()
  │                          │              │        │                   │
  │                          │              │  Store result ────────────▶│ (pub/sub publish)
  │◀── SSE: result ──────────┤◀─────────────│────────│───────────────────┤
  │◀── SSE: progress ────────┤              │        │                   │
  │                          │              └────────┤                   │
  │                          │              finalize_diagnosis_run()     │
  │◀── SSE: complete ────────┤◀─────────────────────────────────────────┤
  │                          │                       │                   │
```

### Per-Ingredient Pipeline (3 stages)

```
Input: ingredient correlation data + user meal history
  │
  ▼
Stage 1: research_ingredient()
  │  Web search enabled, returns medical assessment + citations
  ▼
Stage 2: classify_root_cause()
  │  Uses research as grounding, determines root cause vs confounder
  │
  ├── Confounder → store DiscountedIngredient → publish "discounted" event → done
  │
  ▼
Stage 3: adapt_to_plain_english()
  │  Convert technical diagnosis to user-friendly language
  ▼
Output: DiagnosisResult + DiagnosisCitations → publish "result" event
```

### SSE Channel Convention

- Channel: `diagnosis:{run_id}`
- Event types: `progress`, `result`, `discounted`, `complete`, `error`
- Client subscribes via `EventSource` at `/diagnosis/stream/{run_id}`

### Temporal Lag Windows

Correlation analysis uses medically-grounded time windows:

| Window | Range | Use Case |
|--------|-------|----------|
| Immediate | 0-2 hours | Allergic reactions, intolerances |
| Delayed | 4-24 hours | Digestive issues, IBS triggers |
| Cumulative | 24-168 hours | Inflammatory responses |

---

## 6. Database Relationships

```
User (UUID PK)
├── 1:N  Meal
│         ├── status: draft | published
│         ├── copied_from_id → Meal (self-ref, nullable)
│         └── 1:N  MealIngredient
│                   ├── state: raw | cooked | processed
│                   ├── confidence, source (ai | manual)
│                   └── N:1  Ingredient
│                             ├── normalized_name (unique)
│                             └── N:N  IngredientCategory (via IngredientCategoryRelation)
│                                       └── parent_id → IngredientCategory (self-ref hierarchy)
│
├── 1:N  Symptom
│         ├── tags: JSONB array (type + severity)
│         ├── ai_generated_text, final_notes
│         └── episode_id → Symptom (self-ref, episode continuation)
│
├── 1:N  DiagnosisRun
│         ├── status: pending | processing | completed | failed
│         ├── total_ingredients, completed_ingredients
│         ├── 1:N  DiagnosisResult
│         │         ├── confidence_score (0-1), confidence_level
│         │         ├── immediate/delayed/cumulative_correlation counts
│         │         └── 1:N  DiagnosisCitation
│         │                   └── source_url, source_type (nih | medical_journal | rd_site | other)
│         └── 1:N  DiscountedIngredient
│                   ├── discard_justification
│                   └── confounded_by_ingredient_id → Ingredient
│
├── 1:N  Session
│         └── token (unique), expires_at, user_agent, ip_address
│
├── 1:1  UserSettings
│         └── disclaimer_acknowledged
│
├── 1:N  UserFeedback
│         └── feature_type (meal_analysis | diagnosis_result), rating 0-5
│
├── 1:N  Invite (created_by)
│
└── 1:N  AIUsageLog
          └── model, tokens, estimated_cost_cents, request_type

Standalone:
├── DataExport (user_id, format, status, file_path)
└── EvalRun (eval metrics and results)
```

**Self-referential relationships:**
- `Meal.copied_from_id` → `Meal` (track meal copies)
- `Symptom.episode_id` → `Symptom` (link continuation symptoms to episode)
- `IngredientCategory.parent_id` → `IngredientCategory` (hierarchical categories)

For access control patterns, see [SECURITY.md](SECURITY.md).

---

## 7. State Machines

### Meal Status

```
  create_meal()       publish_meal()
      │                    │
      ▼                    ▼
   [draft] ──────────▶ [published]
```

Draft meals are editable (add/remove ingredients). Publishing locks the ingredient list for correlation integrity.

### Diagnosis Run Status

```
  enqueue_diagnosis()     all tasks complete     any task fails
       │                       │                      │
       ▼                       ▼                      ▼
   [pending] ──▶ [processing] ──▶ [completed]
                       │
                       └──────────────▶ [failed]
```

Progress tracked via `completed_ingredients / total_ingredients`.

### Symptom Elaboration Flow

```
  log symptom        clarify_symptom()          elaborate_on_symptom()
       │              (up to 3 rounds)                  │
       ▼                    │                           ▼
  [initial] ──────▶ [clarify Q&A] ──────▶ [finalized with AI text]
```

The clarification schema uses a discriminated union: responses are either "question mode" (ask follow-up) or "complete mode" (return final elaboration).

---

## 8. Configuration

`app/config.py` — Pydantic `BaseSettings` with `.env` file support:

| Group | Key Settings |
|-------|-------------|
| **Database** | `database_url`, `redis_url` |
| **AI Models** | `haiku_model`, `sonnet_model` (both currently Sonnet 4.5) |
| **AI Timeouts** | `anthropic_timeout` (180s for web search), `anthropic_connect_timeout` (10s) |
| **AI Costs** | `sonnet_input_cost_per_1k` (0.3c), `sonnet_output_cost_per_1k` (1.5c) |
| **Diagnosis** | `diagnosis_min_meals` (2), `diagnosis_min_symptom_occurrences` (2), `diagnosis_max_ingredient_occurrences` (15) |
| **Auth** | `session_secret_key`, `session_cookie_name`, `session_max_age` (7 days), `session_cookie_secure` |

All settings overridable via environment variables.

---

## 9. Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| **Strategy pattern for auth** | `AuthProvider` interface allows swapping LocalAuth for Keycloak/OAuth without touching routes or services |
| **Dramatiq over Celery** | Simpler API, Redis-native broker, fewer dependencies. Sufficient for per-ingredient parallelism |
| **SSE over WebSockets** | Diagnosis progress is unidirectional (server→client). SSE is simpler, auto-reconnects, works through proxies |
| **Prompt caching for diagnosis** | `build_cached_analysis_context()` reuses system prompt + meal history across per-ingredient calls, reducing input token costs |
| **Transaction rollback testing** | Tests run in a transaction that rolls back after each test. No separate test database needed — see [TESTING.md](TESTING.md) |
| **Per-ingredient async pipeline** | Each ingredient analyzed independently (research → classify → adapt). Enables parallelism and granular progress reporting |
| **Pydantic schema validation with retry** | AI responses validated against typed schemas. On validation failure, error context fed back to the model for a corrected response |

---

## 10. Extension Points

### Adding a New AI Feature

1. Define a Pydantic response schema in `app/services/ai_schemas.py`
2. Add a system prompt in `app/services/prompts.py`
3. Add a service method in `ClaudeService` (`app/services/ai_service.py`) using `_call_with_schema_retry()`
4. Add a route in `app/api/` that calls the service method
5. Log usage via `AIUsageService.log_usage()`

### Adding a New Auth Provider

1. Implement `AuthProvider` interface in `app/services/auth/`
2. Override: `authenticate()`, `create_user()`, `get_user_from_request()`, `create_session()`, `revoke_session()`
3. Update `get_auth_provider()` factory in `app/services/auth/__init__.py` to return the new provider based on config

### Adding a New Background Task

1. Define a Dramatiq actor in `app/workers/` with `@dramatiq.actor()`
2. Use the Redis broker (already configured)
3. For progress reporting: publish events via `SSEPublisher` to a named channel
4. Add an SSE endpoint in `app/api/` using `SSESubscriber`

---

## Cross-References

- [DEVOPS.md](DEVOPS.md) — AWS deployment, Docker, nginx configuration
- [SECURITY.md](SECURITY.md) — Access control, secrets, security headers
- [TESTING.md](TESTING.md) — Test patterns, database isolation, CI/CD
- [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md) — UI/UX patterns, htmx/Alpine.js conventions
- [EVALS_STRATEGY.md](EVALS_STRATEGY.md) — AI quality measurement, metrics, datasets
- [STATUS.md](STATUS.md) — Current implementation progress
