# ============================================
# Stage 1: Install dependencies
# ============================================
FROM node:20-slim AS dependencies

WORKDIR /app

# Install build tools needed for better-sqlite3 native compilation
RUN apt-get update && apt-get install -y \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./

RUN npm ci

# ============================================
# Stage 2: Build the Next.js application
# ============================================
FROM node:20-slim AS builder

WORKDIR /app

COPY --from=dependencies /app/node_modules ./node_modules
COPY . .

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Seed the database at build time so the image ships with data.
# The seed script creates ./data/crm.db if it does not exist.
RUN npx tsx src/lib/db/seed.ts
RUN node scripts/create-seed-snapshot.js

RUN npm run build

# ============================================
# Stage 3: Production runner
# ============================================
FROM node:20-slim AS runner

LABEL org.opencontainers.image.source=https://github.com/McGill-NLP/webarena-pro

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=4520
ENV HOSTNAME="0.0.0.0"
ENV RESET_TO_SEED_ON_STARTUP=1

# Copy public assets (not included in standalone output)
COPY --from=builder --chown=node:node /app/public ./public

# Create .next directory owned by node for prerender cache
RUN mkdir -p .next && chown node:node .next

# Copy standalone server + static assets
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

# Copy the seeded SQLite database
COPY --from=builder --chown=node:node /app/data ./data

# Keep an immutable, checkpointed seed snapshot so runtime data volumes can be restored reliably.
COPY --from=builder --chown=node:node /app/data/crm.seed.db ./seed/crm.db

# Startup script restores the DB from snapshot when runtime storage is empty.
COPY --from=builder --chown=node:node /app/scripts/restore-seed-if-empty.js ./scripts/restore-seed-if-empty.js

# HF Spaces runs containers as UID 1000.
# The node user in official Node images is already UID 1000.
USER node

EXPOSE 4520

CMD ["sh", "-c", "node scripts/restore-seed-if-empty.js && node server.js"]
