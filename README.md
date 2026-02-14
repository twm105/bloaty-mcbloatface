# Bloaty McBloatface

A meal tracking and gastro issue diagnosis application. Upload meal images, AI analyzes ingredients, log symptoms, and discover patterns between food and digestive health.

**🚧 Work in Progress - ~80% MVP Complete**

**Recent Updates (Feb 12, 2026):**
- ✅ **Lower analysis thresholds**: Diagnosis now runs with just 2 meals and 2 symptoms (was 3)
- ✅ **UI polish** (Feb 4): Fixed "Add Ingredient" button icon sizing in edit meal view
- ✅ **Diagnosis feature complete** (Feb 3): Full ingredient-symptom correlation analysis with medical grounding

## ✅ What's Working

### Meal Tracking
- **AI-Powered Meal Analysis**: Upload photos → Claude Sonnet 4.5 suggests meal name + ingredients
- **Auto-Accept Workflow**: AI suggestions immediately added (no manual staging)
- **Inline Editing**: Click any field to edit (meal name, ingredients, quantities, location, notes)
- **Provenance Tracking**: 🤖 icons show AI-suggested items, tracked for data science
- **Draft/Published Workflow**: Meals stay as drafts during editing, published on save
- **Meal History**: View published meals with prominent names, subtle dates
- **Ingredient Taxonomy**: 10 root categories (Dairy, Grains, Proteins, etc.)

### Symptom Tracking
- **Tag-Based Entry**: Select symptom tags with autocomplete suggestions
- **Per-Symptom Severity**: 1-10 slider for each symptom tag
- **Per-Symptom Timing**: Individual start/end times with "Apply to all" option
- **Ongoing Symptom Detection**: 3-day lookback window auto-links to previous episodes
- **Episode Linking**: Related symptoms grouped via `episode_id`
- **AI Elaboration**: Streaming AI-generated summaries of symptom entries
- **Symptom History**: View, edit, and delete symptoms with tags, severity, and episode links

### Diagnosis & Pattern Analysis
- **Temporal Correlation Analysis**: SQL-based analysis across immediate/delayed/cumulative windows
- **Confidence Scoring**: Statistical assessment of ingredient-symptom correlations
- **Medical Grounding**: Claude Sonnet 4.5 provides scientific context with citations
- **Citation System**: Links to NIH, PubMed, medical journals with relevance scores
- **User Feedback**: Star ratings and comments for diagnosis quality tracking
- **Results Dashboard**: Ingredient cards with symptoms, medical context, and recommendations

## 🚧 Not Yet Implemented

- ❌ **Timeline Visualizations**: Chart.js integration for trend analysis
- ❌ **GDPR Compliance**: Data export, privacy policy, settings pages
- ❌ **Evals Framework**: AI accuracy testing for meal/symptom analysis
- ❌ **Date Range Filtering**: History pages lack date filtering controls
- ❌ **Test Coverage**: Unit and integration tests needed

**See `docs/STATUS.md` for detailed progress and next priorities.**

## Tech Stack

**Backend**: FastAPI, PostgreSQL, SQLAlchemy, Alembic
**Frontend**: htmx, Alpine.js, Custom CSS (dark theme)
**AI**: Anthropic Claude Sonnet 4.5
**Infrastructure**: Docker Compose

**For architecture decisions and rationale, see `CLAUDE.md`**

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Anthropic API key (get one at https://console.anthropic.com)

### Setup

1. **Clone and configure**
   ```bash
   git clone https://github.com/twm105/bloaty-mcbloatface.git
   cd bloaty-mcbloatface
   ```

2. **Add your Anthropic API key to `.env`**
   ```bash
   echo "ANTHROPIC_API_KEY=sk-ant-api03-..." > .env
   echo "DATABASE_URL=postgresql://postgres:postgres@db:5432/bloaty" >> .env
   ```

   **⚠️ Important:** No quotes around the API key in `.env`

3. **Start the application**
   ```bash
   docker-compose up -d
   ```

4. **Run migrations** (first time only)
   ```bash
   docker-compose exec web alembic upgrade head
   ```

5. **Access the app**
   - 🌐 Web UI: http://localhost:8000
   - 📚 API docs: http://localhost:8000/docs

### Usage

**Meal Logging:**
1. Navigate to http://localhost:8000
2. Click "Log a Meal"
3. Upload a meal photo
4. AI analyzes and suggests name + ingredients (takes ~3-5 seconds)
5. Click any field to edit inline
6. Click "Save Meal" to publish

**Symptom Logging:**
1. Click "Log Symptoms"
2. Type symptom tags (autocomplete suggests common symptoms)
3. Adjust severity per symptom (1-10 slider)
4. Set start/end times (optional "Apply to all")
5. Optionally request AI elaboration
6. Save to track over time

## Development

### Project Structure
```
app/
├── api/                  # FastAPI routes
│   ├── meals.py         # ✅ Meal CRUD + AI analysis + inline editing
│   └── symptoms.py      # ✅ Full CRUD + AI elaboration + episodes
├── models/              # ✅ All SQLAlchemy models complete
├── services/
│   ├── ai_service.py    # ✅ Claude integration (meal analysis)
│   ├── prompts.py       # ✅ Prompt templates with medical ethics
│   ├── meal_service.py  # ✅ Meal CRUD + inline editing
│   └── symptom_service.py # ✅ Full CRUD + episodes + tags
├── static/              # CSS, images
│   └── css/custom.css   # Pill buttons, spinners, disclaimers
└── templates/           # htmx + Alpine.js templates
    ├── meals/           # ✅ Complete UI flow
    └── symptoms/        # ✅ Tag entry, history, editing

alembic/versions/        # ✅ 4 migrations applied
evals/                   # ❌ Not implemented yet
tests/                   # ❌ Not implemented yet
```

### Key Documentation

- **`CLAUDE.md`** - Project vision, architecture decisions, tech stack rationale
- **`docs/STATUS.md`** - Detailed progress tracker with phase completion
- **`docs/DESIGN_PRINCIPLES.md`** - UI/UX design system and guidelines
- **`docs/DEVOPS.md`** - AWS deployment and infrastructure guide
- **`tests/README.md`** - Test organization and coverage roadmap

### Development Commands

```bash
# View logs
docker-compose logs -f web

# Run shell in container
docker-compose exec web bash

# Database migrations
docker-compose exec web alembic revision --autogenerate -m "description"
docker-compose exec web alembic upgrade head

# Check current migration
docker-compose exec web alembic current

# Access PostgreSQL
docker-compose exec db psql -U postgres -d bloaty

# Restart after code changes (auto-reload enabled)
docker-compose restart web
```

### Database Schema

**Core Models**: User, Meal, Ingredient, MealIngredient, Symptom, DiagnosisRun, DiagnosisResult

**For full schema details, see `CLAUDE.md` and migrations in `alembic/versions/`**

## AI Integration

### Cost Analysis
- **Meal analysis**: ~$0.003 per image (Claude Sonnet 4.5)
- **Symptom elaboration**: ~$0.003-0.01 per symptom
- **Pattern analysis**: ~$0.0508 first run, ~$0.0053 cached (not yet implemented)

**Monthly estimate (1 user):**
- 60 meals: $0.18
- 30 symptoms: $0.09-0.30
- 4 analyses: $0.07 (when implemented)
- **Total: ~$0.60/user/month**

### Models Used
- `claude-sonnet-4-5-20250929` for all features
- Originally planned Haiku 3.5, upgraded to Sonnet 4.5 for better accuracy

## Next Steps

**Priority features:**
1. Timeline visualizations and Chart.js integration
2. GDPR compliance (data export, privacy policy)
3. Test coverage (unit & integration tests)
4. Evals framework for AI accuracy

**For detailed roadmap, see `docs/STATUS.md`**

## Contributing

This is a personal project, but suggestions welcome via issues.

## License

TBD
