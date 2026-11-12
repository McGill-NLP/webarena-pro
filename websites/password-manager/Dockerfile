# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
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

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV PORT=8000
EXPOSE $PORT

CMD uvicorn backend.main:app --host 0.0.0.0 --port $PORT
