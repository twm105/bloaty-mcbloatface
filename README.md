# Bloaty McBloatface

A meal tracking and gastro issue diagnosis application. Upload meal images, track ingredients, log symptoms, and discover patterns between food and digestive health.

## Features

- **AI-Powered Meal Analysis**: Upload meal photos, Claude analyzes and suggests ingredients
- **Ingredient Tracking**: Track raw vs cooked ingredients over time
- **Symptom Logging**: Record gastro symptoms and health issues
- **Pattern Analysis**: Correlate ingredients with symptoms to identify trigger foods
- **Analytics Dashboard**: Visualize eating patterns and health trends

## Tech Stack

- **Backend**: FastAPI, PostgreSQL, SQLAlchemy
- **Frontend**: htmx, Alpine.js, Chart.js
- **AI**: Anthropic Claude (Haiku for images, Sonnet for analysis)
- **Infrastructure**: Docker Compose

## Quick Start

1. **Clone and setup**
   ```bash
   git clone <repo-url>
   cd bloaty-mcbloatface
   cp .env.example .env
   ```

2. **Add your Anthropic API key to `.env`**
   ```
   ANTHROPIC_API_KEY=your_key_here
   ```

3. **Start the application**
   ```bash
   docker-compose up --build
   ```

4. **Access the app**
   - Web UI: http://localhost:8000
   - API docs: http://localhost:8000/docs

## Development

### Project Structure
```
app/
├── api/          # FastAPI routes
├── models/       # SQLAlchemy models
├── services/     # Business logic
├── static/       # CSS, JS, images
└── templates/    # HTML templates

evals/
├── data/         # Test data
├── scrapers/     # BBC Good Food scraper
└── run.py        # Evaluation runner

tests/            # Pytest tests
```

### Running Tests
```bash
docker-compose exec web pytest
```

### Running Evals
```bash
docker-compose exec web python -m evals.run --model haiku
```

### Database Migrations
```bash
# Create migration
docker-compose exec web alembic revision --autogenerate -m "description"

# Apply migrations
docker-compose exec web alembic upgrade head
```

## Documentation

See `claude.md` for detailed architecture decisions and development guidelines.

## License

TBD
