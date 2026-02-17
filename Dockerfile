# Stage 1: Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/ .
RUN npm ci
RUN npm run build

# Stage 2: Production image
FROM python:3.12-slim
WORKDIR /app/backend
COPY backend/ .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=frontend-build /app/frontend/dist /app/backend/static/
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
