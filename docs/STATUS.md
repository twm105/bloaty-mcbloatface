# Bloaty McBloatface - Implementation Status

**Last Updated:** February 16, 2026
**Overall Progress:** ~90% MVP Complete
**Recent:** Fixed shared image deletion bug, automated S3 backups, bind mount for uploads

## 🚀 Production Deployment - COMPLETE (Feb 9, 2026)

**Status:** App is live at https://bloaty-app.com

**Infrastructure:**
- EC2 t3.small (Amazon Linux 2023)
- Route 53 DNS
- Let's Encrypt SSL via Certbot
- Secrets Manager for credentials
- S3 bucket for backups (automated daily at 3am)

**Recent Fixes (Feb 16, 2026):**
- ✅ **Shared image deletion bug** - Duplicated meals share `image_path`; deleting one no longer deletes the shared image file (checks reference count first)
- ✅ **Uploads bind mount** - Changed from named Docker volume to `/opt/bloaty/uploads` bind mount for easier backups and EBS snapshots
- ✅ **Automated backups** - `backup.sh` now sources `.env` for S3 bucket config; daily cron job configured
- ✅ **Setup script** - Added cronie install and backup cron job to `setup-ec2.sh`

**Files:**
- `DEVOPS.md` - Full deployment guide
- `deploy/` - Production scripts and configs
- `nginx/conf.d/ssl.conf` - HTTPS configuration

## ✅ Completed Features

### Phase 1: Database Foundation (CRITICAL) - COMPLETE
- ✅ All SQLAlchemy models created and migrated
- ✅ Ingredient taxonomy seeded (10 root categories)
- ✅ Provenance tracking (meal_ingredients.source: ai/manual)
- ✅ AI tracking fields (ai_suggested_ingredients JSONB)
- ✅ Draft/published workflow (meals.status)

### Phase 5: Claude Integration - Meal Analysis - COMPLETE
- ✅ ClaudeService with three methods:
  - validate_meal_image() - checks if image is food
  - analyze_meal_image() - extracts name + ingredients
  - analyze_patterns() - correlation analysis (placeholder)
- ✅ Prompt engineering with medical ethics safeguards
- ✅ Auto-accept workflow (AI suggestions added immediately)
- ✅ Inline editing for all fields (meal name, ingredients, quantities, metadata)
- ✅ Error handling with graceful fallbacks
- ✅ Cost: ~$0.003 per meal with Claude Sonnet 4.5

### UX Enhancements - COMPLETE
- ✅ Linear top-to-bottom flow (image → status → name → ingredients → metadata → save)
- ✅ Compact status indicators (analyzing → complete)
- ✅ Pill-shaped buttons (modern look)
- ✅ Click-to-edit: first click selects all, subsequent clicks position cursor
- ✅ Smooth delete animations (no confirmation popups)
- ✅ History page: meal name prominent, date subtle
- ✅ Draft filtering: only published meals in history

### Phase 6: Symptom Logging with AI - COMPLETE
**Goal:** Structured symptom capture with AI assistance

**Implementation approach:** Tag-based entry with AI elaboration (alternative to original multi-turn Q&A plan)

**Features implemented:**
- ✅ Tag-based symptom selection with autocomplete
- ✅ Per-symptom severity slider (1-10 scale, default 4.0)
- ✅ Per-symptom start/end times with "Apply to all" functionality
- ✅ Ongoing symptom detection (3-day lookback window)
- ✅ Episode linking via `episode_id` field
- ✅ AI elaboration via `/tags/elaborate-stream` endpoint
- ✅ Streaming response for real-time feedback
- ✅ Medical disclaimer and tactful language
- ✅ Full CRUD: create, view history, edit, delete symptoms
- ✅ Database schema: tags (JSONB), severity, start_time, end_time, episode_id, ai_elaborated, clarification_history

**API endpoints:**
- `/symptoms/log` - Symptom logging UI
- `/symptoms/history` - View all symptoms with tags, severity, episode links
- `/symptoms/{id}/edit` - Edit existing symptoms
- `/symptoms/tags/autocomplete` - Tag suggestions
- `/symptoms/tags/elaborate-stream` - AI elaboration (streaming)
- `/symptoms/detect-ongoing` - Detect ongoing symptoms
- `/symptoms/detect-episode` - Detect episode continuation
- `/symptoms/create-tagged` - Create symptom with tags

**Cost:** ~$0.003-0.01 per symptom elaboration with Claude Sonnet 4.5

**Note:** Original plan called for multi-turn conversational clarification. The `clarify_symptom()` method exists in `ai_service.py` but is unused. Tag-based approach provides better UX (faster, more structured) while still leveraging AI.

### Phase 7: History Management - COMPLETE
- ✅ View meal history with inline editing
- ✅ View symptom history with tags, severity, episode links
- ✅ Delete meals and symptoms
- ✅ Edit symptoms (dedicated edit page)
- ⚠️ Missing: Date range filtering, meal editing UI

### Phase 8: Diagnosis Feature - COMPLETE (Feb 3, 2026)
**Goal:** Correlate ingredients with symptoms to identify potential trigger foods

**Implementation:**
- ✅ SQL temporal correlation analysis (immediate/delayed/cumulative windows)
- ✅ Statistical confidence scoring with thresholds
- ✅ Claude Sonnet 4.5 medical grounding with web search
- ✅ Citation storage (NIH, PubMed, medical journals)
- ✅ User feedback system (star ratings + comments)
- ✅ Results UI with ingredient cards, symptoms, medical context
- ✅ Diagnosis history tracking (runs stored in database)

**Technical Solutions:**
- JSON prefill (`{"role": "assistant", "content": "{"}`) forces clean JSON from Claude
- Stop sequences prevent markdown wrapping
- Word limits (300/150/100) prevent token truncation
- Flexible ingredient name matching handles state variations ("raw onion" vs "onion")
- Empty results check skips unnecessary API calls

**API Endpoints:**
- `/diagnosis` - View latest diagnosis results
- `/diagnosis/analyze` - Run new analysis
- `/diagnosis/feedback` - Submit user feedback
- `/diagnosis/methodology` - How it works explainer

**Cost:** ~$0.01-0.03 per diagnosis run (varies with data volume)

### Authentication System - COMPLETE (Feb 8, 2026)
**Goal:** Secure multi-user support before deployment

**Implementation:**
- ✅ Session-based auth with bcrypt password hashing
- ✅ Invite-only registration (admin generates 7-day invite links)
- ✅ Provider abstraction pattern (easy Keycloak migration path)
- ✅ All routes protected with auth dependencies
- ✅ Ownership verification on all data operations
- ✅ Admin functions (password reset, invite management)
- ✅ Account page with change password functionality

**New Files:**
- `app/models/session.py` - Session model for login sessions
- `app/models/invite.py` - Invite model for registration links
- `app/services/auth/` - Auth provider abstraction layer
- `app/api/auth.py` - Login, logout, register, account routes
- `app/templates/auth/` - Login, register, account templates
- `app/cli.py` - Admin user creation command

**Routes:**
- `/auth/login` - Login page
- `/auth/logout` - Logout (clears session)
- `/auth/register?invite=TOKEN` - Invite-only registration
- `/auth/account` - Account management (password change, invite mgmt)

**Migration:** `3b4c5d6e7f8g_add_auth_tables.py`
- Adds password_hash, is_admin to users table
- Creates sessions table
- Creates invites table

**Security:**
- HttpOnly, SameSite cookies
- 7-day session expiry (configurable)
- Generic "Invalid credentials" message (no user enumeration)
- Token-based session with `secrets.token_urlsafe(32)`

**Post-deployment:**
1. Run migration: `alembic upgrade head`
2. Create admin: `python -m app.cli create-admin --email admin@example.com`
3. Set `SESSION_SECRET_KEY` environment variable

### UI/UX Redesign - Dark Theme - COMPLETE (Phase 1)
**Goal:** Transform from Pico.css Notion aesthetic to elegant, minimal dark theme

**Completed:**
- ✅ Comprehensive design system documentation (`DESIGN_PRINCIPLES.md`)
- ✅ CSS architecture overhaul:
  - Created `/app/static/css/design-tokens.css` - All design variables
  - Created `/app/static/css/base.css` - Replaces Pico.css
  - Created modular component CSS (buttons, cards, forms, navigation, badges, images, disclaimers, icons)
- ✅ Icon system - Lucide Icons (409KB sprite, no emojis)
- ✅ Template updates:
  - `base.html` - Dark nav, terracotta disclaimer, removed Pico.css
  - `home.html` - Streamlined (40% less vertical height)
  - `meals/history.html` - Grid layout with circular AI-cropped images
- ✅ Database schema - Added `meal_image_crop_x` and `meal_image_crop_y` columns
- ✅ AI image crop service (`/app/services/image_crop.py`) - Async circular crop detection
- ✅ Migration created (`a1b2c3d4e5f6_add_meal_image_crop_coordinates.py`)

**Design System:**
- 60/30/10 color palette (dark/green/terracotta)
- Typography: 2-4px smaller, lighter weights
- Border radius: 4px/8px/12px/full
- WCAG AAA compliance for contrast
- Responsive grid layouts

**Critical Bug Fixes (Jan 31, 2026):**
- ✅ **Symptom edit page template rendering** - Fixed Jinja2/Alpine.js escaping conflicts by moving template variables to separate `<script>` tag (window.symptomInitData pattern)
- ✅ **Icon sizing** - Fixed SVG icons rendering at intrinsic 300x150px by adding explicit `width="12" height="12" viewBox="0 0 24 24"` attributes to all `.icon-xxs` elements
- ✅ Verified with Playwright browser testing - no console errors, correct rendering

**UI Polish (Feb 4, 2026):**
- ✅ **"Add Ingredient" button icon** - Fixed oversized/misaligned "+" icon in edit meal view by applying proper design system pattern (`icon-xxs` with explicit SVG attributes, reduced from 16px/13px to 12px)

**Template Integration Pattern for Alpine.js + Jinja2:**
```html
<!-- CORRECT: Use script tag for complex data -->
<script>
    window.initData = {
        editing: {{ editing|default(false)|tojson }},
        data: {{ complex_object|tojson }}
    };
</script>
<section x-data="{ editing: window.initData.editing, ... }">

<!-- INCORRECT: Inline Jinja2 in x-data attribute (causes HTML escaping issues) -->
<section x-data="{ editing: {{ editing|tojson }}, ... }">
```

**Still Using Old Design:**
- `/meals/log.html`, `/meals/edit_ingredients.html`
- `/symptoms/log.html`, `/symptoms/history.html`
- `/analysis.html`, `/settings.html`

**Next Steps:**
- Apply migration: `alembic upgrade head`
- Integrate AI crop detection into meal upload endpoint
- Update remaining templates with new design system
- Test responsive design and accessibility

**Documentation:** See `DESIGN_PRINCIPLES.md` for the design system reference

## 🚧 Next Priorities

### Analytics & Visualizations (MEDIUM)
**Goal:** Enhanced data visualization beyond diagnosis results

**Implementation needed:**
1. Timeline view (meals + symptoms chronologically)
2. Chart.js integration for trend analysis
3. Date range filtering for all history pages
4. Export functionality (CSV, PDF reports)

**Files to create:**
- `app/services/analysis_service.py` - SQL correlation queries
- `app/api/analysis.py` - Analysis endpoints
- `app/templates/analysis/view.html` - Main dashboard
- `app/templates/analysis/timeline.html` - Timeline partial
- `app/static/js/charts.js` - Chart.js setup

**Cost:** First analysis ~$0.0508, cached ~$0.0053 (90% savings with prompt caching)

### Phase 9: Evals Framework - COMPLETE (Feb 15, 2026)
**Goal:** Quantify AI accuracy and iterate on prompts

**Implementation:**
- ✅ BBC Good Food scraper (`evals/scrapers/bbc_good_food.py`) - 53 recipes with images
- ✅ Eval runner (`evals/run.py`) with CLI flags (`--prompt-version`, `--notes`, `--no-llm-judge`)
- ✅ Metrics calculator (`evals/metrics.py`) - precision, recall, F1 with LLM-as-judge soft scoring
- ✅ Results stored in eval_runs table with detailed JSONB
- ✅ Prompt versioning infrastructure (`evals/prompts/meal_analysis/`)
- ✅ HTML comparison dashboard (`scripts/generate_eval_report.py`)

**Prompt Iteration Results:**
| Version | F1 | Precision | Recall | Change |
|---------|-----|-----------|--------|--------|
| v1_baseline | 0.429 | 0.616 | 0.353 | — |
| v2_recall_focus | 0.483 | 0.541 | 0.465 | +12.6% F1 |
| v3_recipe_inference | **0.522** | 0.582 | **0.514** | **+21.7% F1** |

**Key Insight:** Ground truth includes recipe ingredients (onion, garlic, stock) not visible in photos. v3 prompts the model to infer typical recipe ingredients based on dish type.

**LLM-as-Judge Scoring:**
- Uses Haiku to score ingredient matches (0, 0.5, 1.0)
- Soft F1 = harmonic mean of soft precision/recall
- Handles semantic equivalence ("ground beef" ↔ "minced beef")

**CLI Usage:**
```bash
# Run eval with specific prompt version
docker compose exec web python -m evals.run eval \
  --eval-type meal_analysis --sample 20 \
  --prompt-version v3_recipe_inference \
  --notes "Recipe inference approach"

# Compare runs
docker compose exec web python -m evals.run compare --runs 1,2,3

# Generate HTML comparison
docker compose exec web python -m scripts.generate_eval_report --run-ids 1,2,3
```

**Documentation:** See `docs/EVALS_STRATEGY.md` for full workflow

### Phase 10: Polish (MEDIUM) - NOT STARTED
- Error handling improvements
- Mobile responsiveness
- Performance optimization
- User testing

## 🗺️ Architecture Overview

### Models (All Complete)
- User, Meal, Ingredient, MealIngredient
- IngredientCategory, IngredientCategoryRelation
- Symptom, UserSettings, DataExport, EvalRun

### Services
- ✅ `ai_service.py` - Claude integration (meal analysis, symptom elaboration, episode detection)
- ✅ `prompts.py` - All prompt templates (meal analysis upgraded to v3_recipe_inference)
- ✅ `meal_service.py` - Meal CRUD + inline editing
- ✅ `symptom_service.py` - Symptom CRUD + episode detection + tag management
- ✅ `file_service.py` - Image handling
- ⚠️ `analysis_service.py` - NOT CREATED (Phase 8)

### API Routes
- ✅ `/meals/*` - Full CRUD + AI analysis + inline editing
- ✅ `/symptoms/*` - Full CRUD + AI elaboration + episode detection + tag autocomplete
- ❌ `/analysis` - NOT CREATED
- ❌ `/settings/*` - NOT CREATED (GDPR exports, disclaimers)

## 📊 Current Status: ~90% MVP Complete

**Working End-to-End:**

**Meal Tracking:**
1. Upload meal photo
2. AI analyzes → suggests name + ingredients
3. Auto-accepted to database
4. Inline editing for all fields
5. Save meal → appears in history

**Symptom Tracking:**
1. Select symptom tags with autocomplete
2. Adjust severity per symptom (1-10 slider)
3. Set per-symptom start/end times
4. Ongoing symptom detection (auto-link to previous episodes)
5. Optional AI elaboration (streaming)
6. Save → appears in history with tags, episode links, AI badges
7. Edit or delete symptoms

**Missing Critical Features:**
- Pattern analysis dashboard (meal-symptom correlations)
- GDPR data export functionality
- Privacy policy and settings pages

## 🔑 Key Design Decisions Made

1. **Auto-accept AI suggestions** - No manual staging, immediate save
2. **Draft/published workflow** - Hide incomplete meals from history
3. **Inline editing** - Click-to-edit with immediate persistence
4. **Provenance tracking** - AI vs manual for data science
5. **Pure htmx** - No script execution in partials (security)
6. **Claude Sonnet 4.5** - For both meal and symptom analysis
7. **Prompt caching** - For pattern analysis only (90% cost savings)
8. **Tag-based symptom entry** - Chose structured tags over conversational Q&A for better UX and data consistency

## 🚨 Known Issues / Tech Debt

### False Positive Correlations in Diagnosis (Priority: Medium)
**Issue:** LLM diagnosis sometimes identifies correlations that are inflated/coincidental rather than causal. Example: chicken flagged as trigger when eaten alongside actual problematic ingredients.

**Root cause:** Statistical correlation ≠ causation. Ingredients frequently eaten together show similar patterns even if only one is the true trigger.

**Improvement needed:**
- Filter ingredient-symptom pairs to include only true causation indicators
- Consider both statistical significance AND medical plausibility
- Possible approaches:
  - Control for co-eaten ingredients (compare eaten together vs separately)
  - Medical knowledge base validation (FODMAP lists, known triggers)
  - Multi-ingredient meal analysis (detect which ingredient is actual trigger)
  - LLM reasoning layer (explicit causation vs coincidence evaluation)

**Status:** Design/architecture decisions needed before implementation

### Recently Fixed
- ✅ Inline editing cursor placement
- ✅ Delete button UX (removed popups, fixed JSON placeholder)
- ✅ Status indicator stacking (analyzing + complete both showing)
- ✅ Draft meals appearing in history
- ✅ Symptom history showing empty (duplicate route in `routes.py` was overriding symptoms router)
- ✅ Symptom edit page template rendering (Jinja2/Alpine.js escaping issue - fixed with script tag pattern)
- ✅ Icon sizing (SVG elements rendering at intrinsic 300x150px - fixed with explicit width/height/viewBox attributes)
- ✅ Incremental diagnosis analysis (skip already-analyzed ingredients on re-runs)
- ✅ Shared image deletion (duplicated meals share image_path; now checks ref count before deleting file)

## 💾 Database State

**Migrations applied:**
- `a02d9fd847b2` - Initial schema (all models)
- `6d7c0be526eb` - Seed ingredient categories
- `61e8ee85c42e` - Add meal name + AI tracking fields
- `5acf901daa38` - Add meal status field
- `c362f51a0834` - Add symptom tags and episodes
- `a20f1e06adcf` - Add AI generated text and final notes to symptoms

**Migrations pending:**
- `a1b2c3d4e5f6` - Add meal image crop coordinates (NOT YET APPLIED)
- `3b4c5d6e7f8g` - Add auth tables (sessions, invites, password_hash, is_admin)

**Sample Data:**
- 10 ingredient categories seeded
- Test meals with AI-analyzed ingredients
- 6 symptoms logged with tags, severity, episode links, and AI elaboration

## 🔐 Environment

**Required:**
- `ANTHROPIC_API_KEY` - Set in `.env` (working)
- `DATABASE_URL` - PostgreSQL connection (working)
- `SESSION_SECRET_KEY` - Required for auth in production (any secure random string)

**Models:**
- `haiku_model=claude-sonnet-4-5-20250929`
- `sonnet_model=claude-sonnet-4-5-20250929`

## 🔮 Future Enhancements (Post-MVP)

### Mobile Camera Integration
**Status:** Planned, not prioritized
**Description:** Add native camera capture for mobile devices (iOS/Android)
- Direct photo capture within the app (vs file upload)
- May require PWA features or native wrapper
- Icon choice: Currently using "Image/Photo" icon (NOT "Camera") to differentiate from this future feature

### Visual Meal Similarity Detection
**Status:** Research needed
**Description:** Detect visually similar meals to flag potential duplicates
- Use case: "Did you already log this meal today?"
- Technical approach: Embedding model (CLIP, ResNet, or similar) to generate image embeddings
- Compare embeddings with cosine similarity
- Alert user if similarity > threshold (e.g., 0.85)
- May require vector database (pgvector extension for PostgreSQL)
- Cost considerations: Embedding API costs vs self-hosted model
- **Do not implement now** - focus on core MVP features first
- Can refine with evals later if needed

## 📝 Next Session TODO

**Immediate priorities:**
1. **Continue Evals Iteration** - Target F1 ≥ 0.77
   - v4_state_focused: Improve state accuracy (currently ~16%)
   - v5_combined: Combine recipe inference with state guidance
   - Expand dataset to 100 images (add AllRecipes scraper)

2. **Analytics & Visualizations**
   - Build timeline view showing meals + symptoms chronologically
   - Add Chart.js visualizations (correlation graphs, heatmaps)

3. **GDPR Compliance**
   - Data export endpoint (`/settings/export`)
   - Privacy policy page
   - User settings page (disclaimer acknowledgment)

**Quick wins:**
- Add date range filtering to meal/symptom history
- Add meal editing UI (currently only inline editing)
- Create settings page for user preferences

---

**To resume development:**
1. `docker-compose up -d`
2. Check current status: `git log --oneline -5`
3. Review this file for next priorities
4. Refer to original plan in session transcript or `/Users/twm/.claude/projects/-Users-twm-Library-CloudStorage-OneDrive-Personal-Coding-Projects-bloaty-mcbloatface/` for detailed requirements
