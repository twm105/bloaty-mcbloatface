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

## Constraints & Guidelines
- **Rapid MVP**: Prioritize speed to working prototype
- **User has final say**: All architectural and design decisions require user approval
- **Track everything**: Ingredient state (raw/cooked), timestamps for correlation analysis
- **Evals from day 1**: Quantify AI performance before building features on top

## Future Considerations
- Authentication system
- Multi-user support
- Mobile app (API-first design makes this easier)
- Advanced ML: Custom models for ingredient detection
- Promptfoo integration for prompt engineering
- Export data (CSV, PDF reports)
- Sharing/collaboration features

## Current Status
- Initial project scaffold created
- Ready to build out directory structure and dependencies
