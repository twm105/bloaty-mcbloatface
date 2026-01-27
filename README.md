# Bloaty McBloatface

A meal tracking and gastro issue diagnosis application. Upload meal images, AI analyzes ingredients, log symptoms, and discover patterns between food and digestive health.

**🚧 Work in Progress - ~40% MVP Complete**

## ✅ What's Working

- **AI-Powered Meal Analysis**: Upload photos → Claude Sonnet 4.5 suggests meal name + ingredients
- **Auto-Accept Workflow**: AI suggestions immediately added (no manual staging)
- **Inline Editing**: Click any field to edit (meal name, ingredients, quantities, location, notes)
- **Provenance Tracking**: 🤖 icons show AI-suggested items, tracked for data science
- **Draft/Published Workflow**: Meals stay as drafts during editing, published on save
- **Meal History**: View published meals with prominent names, subtle dates
- **Ingredient Taxonomy**: 10 root categories (Dairy, Grains, Proteins, etc.)

## 🚧 Not Yet Implemented

- ⚠️ **Symptom Logging**: Basic form exists, but no AI clarification yet
- ❌ **Pattern Analysis**: Correlation dashboard not built
- ❌ **Charts & Visualizations**: No Chart.js integration yet
- ❌ **Medical Disclaimers**: GDPR compliance pages not created
- ❌ **Evals Framework**: AI accuracy testing not implemented

**See `IMPLEMENTATION_STATUS.md` for detailed progress and next priorities.**

## Tech Stack

- **Backend**: FastAPI, PostgreSQL, SQLAlchemy, Alembic
- **Frontend**: htmx, Alpine.js, Pico.css
- **AI**: Anthropic Claude Sonnet 4.5 (~$0.003/meal)
- **Infrastructure**: Docker Compose

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

1. Navigate to http://localhost:8000
2. Click "Log a Meal"
3. Upload a meal photo
4. AI analyzes and suggests name + ingredients (takes ~3-5 seconds)
5. Click any field to edit inline
6. Click "Save Meal" to publish

## Development

### Project Structure
```
app/
├── api/                  # FastAPI routes
│   ├── meals.py         # ✅ Meal CRUD + AI analysis + inline editing
│   └── symptoms.py      # ⚠️ Basic CRUD (missing AI clarification)
├── models/              # ✅ All SQLAlchemy models complete
├── services/
│   ├── ai_service.py    # ✅ Claude integration (meal analysis)
│   ├── prompts.py       # ✅ Prompt templates with medical ethics
│   ├── meal_service.py  # ✅ Meal CRUD + inline editing
│   └── symptom_service.py # ⚠️ Basic CRUD
├── static/              # CSS, images
│   └── css/custom.css   # Pill buttons, spinners, disclaimers
└── templates/           # htmx + Alpine.js templates
    ├── meals/           # ✅ Complete UI flow
    └── symptoms/        # ⚠️ Basic forms only

alembic/versions/        # ✅ 4 migrations applied
evals/                   # ❌ Not implemented yet
tests/                   # ❌ Not implemented yet
```

### Key Files

- `CLAUDE.md` - Original project vision & architecture decisions
- `IMPLEMENTATION_STATUS.md` - Detailed progress tracker (read this!)
- `app/services/prompts.py` - All AI prompts (meal, symptom, pattern analysis)
- `app/services/ai_service.py` - Claude API integration

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

**Core Models:**
- `User` - Single-user MVP (stub for future multi-user)
- `Meal` - name, status (draft/published), timestamp, image_path, ai_suggested_ingredients
- `Ingredient` - Normalized ingredient names
- `MealIngredient` - Junction table with state (raw/cooked/processed) and source (ai/manual)
- `IngredientCategory` - Taxonomy (self-referencing tree)
- `Symptom` - Raw description, structured type, severity, clarification_history

**See migrations in `alembic/versions/` for full schema.**

## AI Integration

### Cost Analysis
- **Meal analysis**: ~$0.003 per image (Claude Sonnet 4.5)
- **Symptom clarification**: ~$0.0126 per symptom (not yet implemented)
- **Pattern analysis**: ~$0.0508 first run, ~$0.0053 cached (not yet implemented)

**Monthly estimate (1 user):**
- 60 meals: $0.18
- 30 symptoms: $0.38 (when implemented)
- 4 analyses: $0.07 (when implemented)
- **Total: ~$0.60/user/month**

### Models Used
- `claude-sonnet-4-5-20250929` for all features
- Originally planned Haiku 3.5, upgraded to Sonnet 4.5 for better accuracy

## Next Steps

**Immediate priorities (see `IMPLEMENTATION_STATUS.md`):**
1. Implement symptom clarification (Phase 6)
2. Build pattern analysis dashboard (Phase 8)
3. Add medical disclaimers & GDPR compliance
4. Create evals framework (BBC Good Food scraper)

## Contributing

This is a personal project, but suggestions welcome via issues.

## License

TBD
