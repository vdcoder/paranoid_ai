.PHONY: help install dev test lint format run docker-build docker-run clean

help:
	@echo "Available commands:"
	@echo "  install      - Install production dependencies"
	@echo "  dev          - Install development dependencies"
	@echo "  test         - Run tests with coverage"
	@echo "  lint         - Run linters (ruff, mypy)"
	@echo "  format       - Format code with black"
	@echo "  run          - Run the API server locally"
	@echo "  docker-build - Build Docker image"
	@echo "  docker-run   - Run with docker-compose"
	@echo "  clean        - Clean build artifacts"

install:
	pip install -e .

dev:
	pip install -e ".[dev]"
	pre-commit install

test:
	pytest

lint:
	ruff check src/ tests/
	mypy src/

format:
	black src/ tests/
	ruff check --fix src/ tests/

run:
	python -m paranoid_ai.api

docker-build:
	docker-compose build

docker-run:
	docker-compose up

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache/ .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
