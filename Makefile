.PHONY: help build up down logs shell test migrate revision evals nginx-logs nginx-reload

help:
	@echo "Bloaty McBloatface - Development Commands"
	@echo ""
	@echo "  make build        - Build Docker containers"
	@echo "  make up           - Start all services"
	@echo "  make down         - Stop all services"
	@echo "  make logs         - View container logs"
	@echo "  make shell        - Open shell in web container"
	@echo "  make test         - Run pytest tests"
	@echo "  make migrate      - Run database migrations"
	@echo "  make revision     - Create new migration (use MSG='description')"
	@echo "  make evals        - Run evaluation suite"
	@echo "  make nginx-logs   - Tail nginx access and error logs"
	@echo "  make nginx-reload - Reload nginx config without restart"

build:
	docker-compose build

up:
	docker-compose up -d
	@echo "App running at http://localhost"

down:
	docker-compose down

logs:
	docker-compose logs -f

shell:
	docker-compose exec web /bin/bash

test:
	docker-compose exec web pytest

migrate:
	docker-compose exec web alembic upgrade head

revision:
	docker-compose exec web alembic revision --autogenerate -m "$(MSG)"

evals:
	docker-compose exec web python -m evals.run

nginx-logs:
	docker-compose exec nginx tail -f /var/log/nginx/access.log /var/log/nginx/error.log

nginx-reload:
	docker-compose exec nginx nginx -s reload
