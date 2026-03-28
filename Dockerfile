FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy the application code and runtime assets.
COPY app ./app
COPY prompts ./prompts
COPY run.py ./
COPY README.md ./

ENV PYTHONUNBUFFERED=1
ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000
ENV ENABLE_SCHEDULER=false

EXPOSE 8000

CMD [".venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
