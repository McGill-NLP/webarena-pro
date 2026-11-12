FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright XDG_CACHE_HOME=/opt/cache
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
COPY wheels/ /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels
RUN webarena-pro-mcp install && python -m playwright install-deps chromium
WORKDIR /opt/webarena
CMD ["webarena-pro-harbor", "serve", "--config", "/opt/webarena/episode.json"]
