# Bloaty McBloatface - Project Context

## Project Overview
A containerized web application for meal tracking and gastro issue diagnosis. Users upload meal images, AI analyzes ingredients, and the system correlates ingredients with health symptoms over time to identify potential trigger foods.

## Core Features
1. **Meal Logging**: Upload meal images, AI proposes ingredients list, user refines
2. **Health/Symptom Tracking**: Separate log for gastro and other health symptoms
3. **Pattern Analysis**: Correlate ingredients with symptoms to identify triggers
4. **Analytics Dashboard**: Visualize meals, symptoms, and correlations over time

## Tech Stack

### Backend
- **FastAPI**: Python web framework
- **PostgreSQL**: Relational database for structured data (users, meals, ingredients, symptoms)
- **SQLAlchemy**: ORM for database interactions
- **Alembic**: Database migrations

### Frontend
- **htmx**: Dynamic interactivity without build tools
- **Alpine.js**: Lightweight reactive components
- **Tailwind CSS** or **Pico.css**: Styling (TBD)
- **Chart.js**: Analytics visualizations

#### Icon Sizing (IMPORTANT)
Icons use Lucide sprite SVGs. **Always specify explicit dimensions** to prevent oversized rendering:
```html
<!-- Correct: explicit width/height + viewBox + overflow -->
<svg width="16" height="16" viewBox="0 0 24 24" class="icon icon-sm" style="overflow: visible;">
    <use href="/static/icons/lucide-sprite.svg#icon-name"></use>
</svg>

<!-- Wrong: relying only on CSS class - may render too large -->
<svg class="icon icon-sm">
    <use href="/static/icons/lucide-sprite.svg#icon-name"></use>
</svg>
```
Size reference (match to context):
- **12x12**: Tiny inline icons (trash buttons in cards)
- **14x14**: Small inline icons (checkmarks, status indicators)
- **16x16**: Standard icons (alerts, buttons, navigation)
- **20x20+**: Large feature icons (page headers)

Always add `overflow: visible` to prevent clipping if viewBox doesn't align perfectly.

### AI/ML
- **Anthropic Claude API**:
  - Haiku: Image analysis (meal → ingredients)
  - Sonnet: Symptom analysis and diagnosis
  - Future: Can uplift to Opus if needed

### Infrastructure
- **Docker Compose**: Container orchestration
- **nginx**: Reverse proxy (if needed)

## Architecture Decisions

### Database Schema (Initial)
```
Users
├── Meals (1:many)
│   └── MealIngredients (many:many)
│       └── Ingredients
│           ├── name: str
│           ├── state: enum (raw, cooked, processed)
└── SymptomLogs (1:many)
    ├── timestamp
    ├── symptom_type
    ├── severity
    └── notes
```

### Key Design Decisions
1. **Relational over NoSQL**: Data is structured, needs JOINs for correlation analysis
2. **htmx over React**: Faster MVP, no build complexity, sufficient for forms/tables/charts
3. **Native evals over promptfoo**: Simpler setup, store results in PostgreSQL, easier to customize
4. **Auth later**: Focus on core functionality first, add authentication post-MVP
5. **Ingredient state tracking**: Track raw/cooked/processed to improve correlation accuracy
6. **Minimize vertical length**: Reduce vertical UI clutter by showing contextual controls only when needed, not preemptively. Keep forms compact and focused on primary inputs.

## Development Approach

### Evals-First Development
- Create `evals/` directory from the start
- Scrape BBC Good Food for test data (images + ingredient lists)
- Test runner calls image analysis endpoint
- Metrics: precision, recall, F1 for ingredients; accuracy for raw/cooked state
- Store eval runs in PostgreSQL for tracking over time
- CLI: `python -m evals.run --model haiku`

### Project Structure
```
bloaty-mcbloatface/
├── app/
│   ├── api/          # FastAPI routes
│   ├── models/       # SQLAlchemy models
│   ├── services/     # Business logic (Claude API, analysis)
│   ├── static/       # CSS, JS, images
│   └── templates/    # HTML templates
├── evals/
│   ├── data/         # Scraped test data
│   ├── run.py        # Eval runner
│   └── metrics.py    # Scoring logic
├── alembic/          # DB migrations
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Documentation

Project documentation lives in the `docs/` folder:

**docs/STATUS.md** - Implementation status and progress tracking
- Reference at session start to understand current project state
- Check when deciding what to work on next
- Update after completing features to track progress

**docs/DESIGN_PRINCIPLES.md** - UI/UX design system and patterns
- Reference when implementing any UI/UX changes
- Consult when adding new components or pages
- Check when debugging rendering issues (Alpine.js/Jinja2 patterns, icon sizing)

**docs/DEVOPS.md** - AWS deployment and infrastructure guide
- Reference when deploying or updating production
- Consult when troubleshooting infrastructure issues
- Check when modifying Docker/nginx configuration

**docs/TESTING.md** - Testing strategy and patterns
- Reference when writing or organizing tests
- Consult for database isolation, API caching, and fixture patterns
- Check for CI/CD and coverage requirements

## Dependencies to Add
- fastapi[all]
- sqlalchemy
- alembic
- psycopg2-binary
- anthropic
- python-multipart (file uploads)
- pillow (image processing)
- beautifulsoup4 (scraping)
- requests
- pytest (testing)
- httpx (async requests)

## Analytics Requirements
- Time-series queries (PostgreSQL window functions)
- Correlation analysis (ingredients vs symptoms with time lags)
- Aggregations: ingredient frequency, symptom severity over time
- Chart.js for frontend visualization
- Interactive filtering (date ranges, ingredient selection)

## Diagnosis Feature Planning

### Phase 1: AI Correlation Analysis (MVP)
**Backend Analysis Engine:**
- SQL windowing approach: For each symptom, aggregate ingredients eaten across multiple temporal lag windows
  - Immediate lag: 0-2 hours (allergic reactions, intolerances)
  - Delayed lag: 4-24 hours (digestive issues, IBS triggers)
  - Cumulative lag: days/weeks (inflammatory responses)
  - Lag windows grounded in dietitian/medical research
- Statistical confidence scoring with thresholds (data volume + statistical significance)
- Ingredient state consideration (raw vs cooked vs processed)
- Web search integration for medical grounding (constrained to trusted domains: NIH, medical journals, RD organizations)
- Citations with hyperlinks and hover footnotes for ethical transparency

**Simple Results View:**
- List/table of suspected triggers ranked by confidence
- Confidence visualization using color scale (per design principles)
- Citations displayed as hyperlinked sources with brief pop-over footnotes
- User feedback mechanism: 0-5 star rating + optional text justification per diagnosis
- Results only shown when confidence threshold met (prevents premature/unreliable diagnoses)
- All symptom types included from start

**Methodology Page:**
- "How Diagnosis Works" explainer linked from diagnosis page
- Layman's terms explanation of temporal lag analysis, statistical methods, and grounding approach

### Phase 2: Visual Timeline (Future)
**Deferred for post-MVP development:**
- Interactive scrolling timeline: meals above centerline, symptoms below
- Meals expandable to show ingredients; suspected triggers highlighted
- Symptoms as points (acute) or bars (enduring) with severity visualization
- Granularity options: hourly vs daily views with zoom
- Interactive filtering: date range, symptom type, ingredient type
- Connection visualization: lines/highlighting from trigger ingredients to symptoms
- Hover interactions to explore cause → effect relationships
- Color-coded confidence levels for correlations

## Constraints & Guidelines
- **Rapid MVP**: Prioritize speed to working prototype
- **User has final say**: All architectural and design decisions require user approval
- **Critical judgment**: Apply critical thinking to user inputs. Be polite but not sycophantic. Test alternative ideas where they exist without delaying development. User has final say.
- **Track everything**: Ingredient state (raw/cooked), timestamps for correlation analysis
- **Evals from day 1**: Quantify AI performance before building features on top
- **Design Principles**: Refer to docs/DESIGN_PRINCIPLES.md whenever applying UX or UI design

## Future Considerations
- Authentication system
- Multi-user support
- Mobile app (API-first design makes this easier)
- Advanced ML: Custom models for ingredient detection
- Promptfoo integration for prompt engineering
- Export data (CSV, PDF reports)
- Sharing/collaboration features

## Current Status
- ~85% MVP Complete (see docs/STATUS.md for details)
- Working features: Meal tracking with AI analysis, symptom logging with AI elaboration, history management, diagnosis with AI correlation analysis, authentication system
- Recent: Production deployment to AWS, reduced diagnosis thresholds for faster onboarding
- Next priority: Analytics & visualizations, evals framework
- See README.md and docs/STATUS.md for current progress
