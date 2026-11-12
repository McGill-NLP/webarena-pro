FROM node:20-bookworm-slim AS build
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
COPY prisma ./prisma
RUN npm ci

COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
ENV PASSWORD_SALT=change_me
ENV DATABASE_URL=postgresql://webarena:webarena@127.0.0.1:5432/webarena?schema=public
RUN sh -c 'for i in 1 2 3; do npm run prisma:generate && exit 0; echo "prisma generate failed, retrying..." >&2; sleep 5; done; exit 1'
RUN npm run build \
    && test -s .next/server/app/api/eval/state/route.js

FROM node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-15 \
    postgresql-client-15 \
    openssl \
    ca-certificates \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /app /app

ENV NEXT_TELEMETRY_DISABLED=1
ENV PASSWORD_SALT=change_me
ENV PGDATA=/app/.pgdata
ENV DATABASE_URL=postgresql://webarena:webarena@127.0.0.1:5432/webarena?schema=public

RUN mkdir -p /app/.pgdata /var/run/postgresql \
    && chown -R postgres:postgres /app/.pgdata /var/run/postgresql \
    && su postgres -c "/usr/lib/postgresql/15/bin/initdb -D /app/.pgdata" \
    && printf "listen_addresses='127.0.0.1'\n" >> /app/.pgdata/postgresql.conf \
    && printf "local all all trust\nhost all all 127.0.0.1/32 scram-sha-256\n" >> /app/.pgdata/pg_hba.conf \
    && su postgres -c "/usr/lib/postgresql/15/bin/pg_ctl -D /app/.pgdata -l /tmp/postgres-build.log start" \
    && until pg_isready -h 127.0.0.1 -p 5432 -U postgres; do sleep 1; done \
    && su postgres -c "psql -c \"CREATE USER webarena WITH PASSWORD 'webarena';\"" \
    && su postgres -c "psql -c \"CREATE DATABASE webarena OWNER webarena;\"" \
    && npm run prisma:deploy \
    && npm run db:seed \
    && su postgres -c "/usr/lib/postgresql/15/bin/pg_ctl -D /app/.pgdata stop -m fast"

COPY docker-entry-seeded.sh /app/docker-entry-seeded.sh
RUN chmod +x /app/docker-entry-seeded.sh

EXPOSE 3000
ENTRYPOINT ["/app/docker-entry-seeded.sh"]
CMD ["start"]
