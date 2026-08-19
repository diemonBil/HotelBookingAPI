.PHONY: help install run test cov lint format migrate seed schema up down logs

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Install development dependencies
	pip install -r requirements-dev.txt

run:  ## Start the development server
	python manage.py runserver

test:  ## Run the test suite
	pytest

cov:  ## Run the test suite with a coverage report
	pytest --cov --cov-report=term --cov-report=html

lint:  ## Check style and imports
	ruff check .
	ruff format --check .

format:  ## Reformat the code
	ruff check --fix .
	ruff format .

migrate:  ## Apply database migrations
	python manage.py migrate

seed:  ## Load the demo dataset
	python manage.py seed_demo_data

schema:  ## Write the OpenAPI schema to schema.yaml
	python manage.py spectacular --fail-on-warn --file schema.yaml

up:  ## Start the full stack in Docker
	docker compose up --build -d

down:  ## Stop the stack
	docker compose down

logs:  ## Follow the application logs
	docker compose logs -f web
