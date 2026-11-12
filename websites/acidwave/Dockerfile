# syntax=docker/dockerfile:1.7
# Build: docker build --secret id=hf_token,env=HF_TOKEN -t acidwave-webarena .
# Run:   docker run -d --name acidwave -p 3000:80 acidwave-webarena
# Reset: docker rm -f acidwave && docker run -d --name acidwave -p 3000:80 acidwave-webarena

# ── Stage 1: Build frontend ────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build
COPY acidwave-app/package*.json ./acidwave-app/
RUN cd acidwave-app && npm install
COPY acidwave-app/ ./acidwave-app/
COPY database/ ./database/
COPY scripts/ ./scripts/
RUN --mount=type=secret,id=hf_token node scripts/download-hf-audio.mjs
RUN cd acidwave-app && npm run build

# ── Stage 2: Runtime image ─────────────────────────────────────────────────────
FROM node:20-alpine

RUN apk add --no-cache postgresql postgresql-client nginx

WORKDIR /app

# Install backend
COPY backend/package*.json ./backend/
RUN cd backend && npm install --omit=dev
COPY backend/ ./backend/

# Copy built frontend
COPY --from=frontend-builder /build/acidwave-app/dist /usr/share/nginx/html

# Nginx config
COPY nginx.conf /etc/nginx/http.d/default.conf

# Database files
COPY database/schema.sql /tmp/schema.sql
COPY database/seed.sql /tmp/seed.sql

# Bake PostgreSQL data into the image
ENV PGDATA=/var/lib/postgresql/data
RUN mkdir -p "$PGDATA" /var/run/postgresql /run/nginx /var/log/postgresql \
    && touch /var/log/postgresql/postgresql.log \
    && chown -R postgres:postgres "$PGDATA" /var/run/postgresql /var/log/postgresql \
    && su postgres -s /bin/sh -c "initdb -D $PGDATA --username=postgres --encoding=UTF8 --locale=C" \
    && su postgres -s /bin/sh -c "pg_ctl start -D $PGDATA -w -l /var/log/postgresql/postgresql.log -o '-k /var/run/postgresql'" \
    && su postgres -s /bin/sh -c "psql -c 'CREATE DATABASE acidwave;'" \
    && su postgres -s /bin/sh -c "psql -d acidwave -f /tmp/schema.sql" \
    && su postgres -s /bin/sh -c "psql -d acidwave -f /tmp/seed.sql" \
    && su postgres -s /bin/sh -c "pg_ctl stop -D $PGDATA -m fast"

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80

CMD ["/entrypoint.sh"]
