backend-start:
	@echo "Starting development server..."
	./.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000

frontend-start:
	@echo "Starting frontend development server..."
	cd frontend && npm run dev