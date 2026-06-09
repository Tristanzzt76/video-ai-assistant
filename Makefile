.PHONY: install dev-backend dev-frontend dev test build up down clean

install:
	pip install -r requirements.txt

dev-backend:
	uvicorn app:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

dev:
	uvicorn app:app --reload --port 8000 & cd frontend && npm run dev

test:
	pytest tests/ -v

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
