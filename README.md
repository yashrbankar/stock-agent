# Stock Bot

A modular FastAPI service that screens NSE stocks near their 52-week lows using NSE market data,
analyzes shortlisted names with Gemini plus Google Search grounding, and sends a formatted report
by email.

## Features

- FastAPI endpoints for health, stock inspection, and manual runs
- Prompt files stored outside code in `/prompts`
- Gemini analysis with `google_search`
- Daily scheduler at 08:30
- SMTP email delivery with optional WhatsApp hook placeholder
- `uv`-friendly project setup

## Quick Start

1. Install dependencies:

```bash
uv sync
```

2. Copy the environment template and fill in your secrets:

```bash
cp .env.example .env
```

3. Start the API:

```bash
uv run run.py
```

4. Open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/stocks`
- `http://127.0.0.1:8000/run`

## Docker Quick Start

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Build the image:

```bash
docker compose build
```

3. Start the container:

```bash
docker compose up
```

4. Open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/stocks`
- `http://127.0.0.1:8000/run`

Notes:

- `ENABLE_SCHEDULER=false` is the default for Docker so the web container does not run the daily job.
- For production on Azure, keep the web app container focused on serving HTTP and run the schedule separately.
- To stop the stack, use `docker compose down`.

## Azure Container Direction

Recommended production flow:

1. Build this repo into a Docker image.
2. Push the image to Azure Container Registry.
3. Deploy the image to Azure Container Apps or Azure App Service for Containers.
4. Configure secrets as environment variables in Azure.
5. Run the daily stock job outside the web container using GitHub Actions or an Azure-native scheduled job.

## GitHub Actions

This repo includes a GitHub Actions automation at `.github/workflows/daily-stock-run.yml`.

- It runs every day at 08:45 IST.
- It also supports manual runs from the Actions tab.
- It writes a `.env` file from the `ENV_FILE` repository secret.
- It invokes the FastAPI `/run` route, which executes the stock pipeline and sends email notifications.

Required GitHub repository secret:

- `ENV_FILE`: the full contents of your production `.env` file

## Screening Logic

- Scans only the configured NSE indices, deduplicated into one universe
- Keeps only stocks that are within the configured distance from their 52-week low
- Sends every near-low stock to Gemini for a simple fundamental breakdown

## Notes

- The NSE site is unofficial for direct API use and can rate-limit or change behavior. This project
  uses retry logic and browser-like headers, but you should expect occasional upstream instability.
- Gemini analysis requires `GEMINI_API_KEY`.
- Email delivery requires SMTP credentials in `.env`.
