.PHONY: install dev-backend dev-frontend dev eval upload-docs test build up down clean

install:
	pip install -r requirements.txt

dev-backend:
	HF_HUB_DISABLE_XET=1 .venv/bin/uvicorn app:app --port 8000 --reload

dev-frontend:
	cd frontend && npm run dev

dev:
	@echo "启动后端 http://localhost:8000 ..."
	HF_HUB_DISABLE_XET=1 .venv/bin/uvicorn app:app --port 8000 --reload &
	@echo "启动前端 http://localhost:3000 ..."
	cd frontend && npm run dev &
	@echo "服务启动中，请稍等 30 秒..."
	@echo "API 文档: http://localhost:8000/docs"

eval:
	HF_HUB_DISABLE_XET=1 .venv/bin/python -u evaluation/evaluate.py --mode compare_all

upload-docs:
	@echo "上传知识库文档..."
	@for doc in data/docs/*.md data/docs/*.pdf; do \
		[ -f "$$doc" ] && curl -s -X POST http://localhost:8000/api/v1/upload -F "file=@$$doc" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'  ✓ {d[\"filename\"]} ({d[\"chunk_count\"]} chunks)')" 2>/dev/null || true; \
	done

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
