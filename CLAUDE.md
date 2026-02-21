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
- **FastAPI** (Python), **PostgreSQL**, **SQLAlchemy**, **Alembic**
- **Redis** (message broker + SSE pub/sub), **Dramatiq** (background tasks)

### Frontend
- **htmx** + **Alpine.js** — dynamic interactivity without build tools
- **Custom CSS design system** — dark theme, 60/30/10 palette (see docs/DESIGN_PRINCIPLES.md)
- **Lucide Icons** (sprite SVG) — see docs/DESIGN_PRINCIPLES.md for icon sizing rules
- **Chart.js** — analytics visualizations

### AI/ML
- **Anthropic Claude Sonnet** — all AI features (meal analysis, symptom elaboration, diagnosis)

### Infrastructure
- **Docker Compose** — five containers (web, db, redis, worker, nginx)
- **nginx** — reverse proxy, TLS termination, static files, security headers
- **AWS** — EC2, Route 53, S3 backups, Secrets Manager (see docs/DEVOPS.md)

### Package Management
- **uv**: Fast Python package manager (https://docs.astral.sh/uv/)
  - Install dependencies: `uv sync`
  - Install with dev deps: `uv sync --all-extras`
  - Run commands: `uv run <command>`
  - Add dependency: `uv add <package>`

### Development Environment (IMPORTANT)
Python code must run inside the Docker web container to access PostgreSQL and other services:
```bash
# Run tests
docker compose exec web pytest tests/ -v

# Run lint check
docker compose exec web ruff check .

# Run format check
docker compose exec web ruff format --check .

# Run any Python command
docker compose exec web python -m <module>

# Interactive shell
docker compose exec web bash
```
Do NOT run pytest or python directly on the host - it will fail to connect to the database.
**Always run tests, lint, and format check** before considering work complete.

### CI Status Check (IMPORTANT)
At the start of each session, check if CI is green:
```bash
gh run list --limit 1 --json conclusion,status,name,headBranch -q '.[] | "\(.status)/\(.conclusion) - \(.name) on \(.headBranch)"'
```
- `completed/success` - CI green, proceed normally
- `completed/failure` - notify user, prioritize fixing before new work
- `in_progress/` - CI running, check back later or proceed with caution

### Database Migrations (IMPORTANT)
The local PostgreSQL database persists data in a Docker volume. **Do NOT wipe user data.**

```bash
# SAFE - only runs NEW migrations, preserves data
docker compose exec web alembic upgrade head

# DANGEROUS - wipes all data, reruns all migrations from scratch
# Only use if explicitly asked or DB is corrupted beyond repair
docker compose exec web alembic stamp base && alembic upgrade head
```

If `alembic upgrade head` fails with "table does not exist", ask the user before running destructive commands - they may have test data they want to preserve.

## Documentation

Project documentation lives in the `docs/` folder:

**docs/STATUS.md** - Implementation status and progress tracking (SOURCE OF TRUTH)
- Reference at session start to understand current project state
- Check when deciding what to work on next
- **IMPORTANT: Update after completing work each session:**
  - Update the "Last Updated" date and "Recent" summary line
  - Move completed items from "Next Priorities" to "Completed Features"
  - Update the overall progress percentage if scope changed
  - This is the single source of truth for project status — do NOT duplicate status info elsewhere

**docs/DESIGN_PRINCIPLES.md** - UI/UX design system and patterns
- Reference when implementing any UI/UX changes
- Consult when adding new components or pages
- Check when debugging rendering issues (Alpine.js/Jinja2 patterns, icon sizing)

**docs/ARCHITECTURE.md** - Internal system architecture and component design
- Reference when understanding how layers connect (routes → services → models)
- Consult when adding new features or services
- Check for async processing patterns (Dramatiq, SSE) and AI integration details

**docs/DEVOPS.md** - AWS deployment and infrastructure guide
- Reference when deploying or updating production
- Consult when troubleshooting infrastructure issues
- Check when modifying Docker/nginx configuration

**docs/TESTING.md** - Testing strategy and patterns
- Reference when writing or organizing tests
- Consult for database isolation, API caching, and fixture patterns
- Check for CI/CD and coverage requirements
- **Before merging to main**: Read merge workflow section for test validation steps

**docs/EVALS_STRATEGY.md** - AI evaluation framework
- Reference when implementing or running evals
- Consult for metrics definitions and target thresholds
- Check for dataset requirements and CLI usage

**docs/SECURITY.md** - Security architecture and developer guidance (public)
- Reference when adding routes, handling user input, or working with AI features
- Consult for authentication patterns, secrets management, and security headers
- Check the PR security checklist before submitting changes

**docs/SECURITY_INTERNAL.md** - Operational security details (gitignored, not committed)
- Known gaps, hardening roadmap, infrastructure specifics, incident history
- Supplements SECURITY.md — read that first
- **Never commit vulnerability details, infrastructure specifics, or security gaps to public docs — these belong in SECURITY_INTERNAL.md only**

**docs/PRIVACY.md** - Data practices and privacy information
- Reference when handling user data, images, or health information
- Consult when adding new data collection or AI processing features

## Constraints & Guidelines
- **User has final say**: All architectural and design decisions require user approval
- **Critical judgment**: Apply critical thinking to user inputs. Be polite but not sycophantic. Test alternative ideas where they exist without delaying development. User has final say.
- **Track everything**: Ingredient state (raw/cooked), timestamps for correlation analysis
- **Design Principles**: Refer to docs/DESIGN_PRINCIPLES.md whenever applying UX or UI design
- **Minimize vertical length**: Reduce vertical UI clutter by showing contextual controls only when needed. Keep forms compact and focused on primary inputs.
