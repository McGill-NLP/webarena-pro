# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir \
    flask==3.0.0 \
    werkzeug==3.0.1 \
    huggingface_hub

RUN --mount=type=secret,id=hf_token,required=true \
    HF_TOKEN="$(cat /run/secrets/hf_token)" python fetch_assets.py

RUN python -c "from app import app; assert any(r.rule == '/api/eval/state' and 'GET' in r.methods for r in app.url_map.iter_rules())"

EXPOSE 7860

CMD ["python", "app.py"]
