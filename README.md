# Stock Bot

A modular FastAPI service that screens NSE stocks near their 52-week lows, enriches them with
fundamentals from Yahoo Finance, analyzes shortlisted names with Gemini plus Google Search
grounding, and sends a formatted report by email.

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

## GitHub Actions

This repo includes a GitHub Actions pipeline at `.github/workflows/ci-cd.yml`.

- CI runs on every push to `main`, every pull request, and manual workflow runs.
- CD is optional and triggers only if you add a repository secret named `DEPLOY_WEBHOOK_URL`.

Recommended GitHub repository secrets:

- `ENV_FILE`: optional full `.env` file content for workflow smoke tests
- `DEPLOY_WEBHOOK_URL`: optional deploy hook URL from your hosting platform

If `ENV_FILE` is not set, the workflow falls back to `.env.example`.

## Notes

- The NSE site is unofficial for direct API use and can rate-limit or change behavior. This project
  uses retry logic and browser-like headers, but you should expect occasional upstream instability.
- Gemini analysis requires `GEMINI_API_KEY`.
- Email delivery requires SMTP credentials in `.env`.
