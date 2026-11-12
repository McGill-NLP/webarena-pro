FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=core.settings \
    DJANGO_ALLOWED_HOSTS=* \
    PORT=8000 \
    SEED_DATA=1 \
    SEED_RESET=0

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY . /app

RUN chmod +x /app/scripts/docker-entrypoint.sh /app/scripts/seed_data.sh \
    && mkdir -p /app/media /app/staticfiles

# Run migrations and data import once, then keep an immutable reset snapshot.
RUN /app/scripts/docker-entrypoint.sh python -c "import django; django.setup(); from core.seed_snapshot import create_seed_snapshot; create_seed_snapshot()"

EXPOSE 8000

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
