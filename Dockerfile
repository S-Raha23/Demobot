# DemoBot judge mode: one image for a Hugging Face Space (Docker SDK, port 7860).
# Stage 1 builds the frontend; stage 2 runs FastAPI, which serves the built frontend, the API,
# the baked runs and the Panda assets.

FROM node:20.18.1-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build

FROM python:3.11.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

# Hugging Face runs the container as user 1000
RUN useradd -m -u 1000 user
WORKDIR /app
COPY --chown=user pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project && chown -R user /app
COPY --chown=user backend/ backend/
COPY --chown=user assets/ assets/
COPY --chown=user docs/skill_api.md docs/skill_api.md
COPY --chown=user eval/ eval/
RUN uv sync --frozen --no-dev && chown -R user /app
COPY --from=web --chown=user /web/dist frontend/dist

USER user
ENV DEMOBOT_MODE=judge \
    DATA_DIR=/tmp/demobot \
    PYTHONUNBUFFERED=1 \
    HOME=/home/user
EXPOSE 7860
CMD ["/app/.venv/bin/uvicorn", "demobot.api:app", "--host", "0.0.0.0", "--port", "7860", "--app-dir", "backend"]
