# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Run backend + serve frontend
FROM python:3.12-slim
WORKDIR /app

# Install Python deps
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend
COPY backend/ ./backend/
COPY airline_routes.json ./

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV PORT=7860
EXPOSE $PORT

CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT
