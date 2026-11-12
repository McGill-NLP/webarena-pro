FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=4230

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Generate the expanded catalog once; episode resets restore this SQLite snapshot.
RUN python -c "from app.seed import ensure_database_seeded, create_seed_snapshot; ensure_database_seeded(); create_seed_snapshot()"
RUN python -c "from app.main import app; assert any(r.path == '/api/eval/state' and 'GET' in r.methods for r in app.routes)"

EXPOSE 4230

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4230"]
