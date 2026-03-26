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

This repo includes a GitHub Actions automation at `.github/workflows/daily-stock-run.yml`.

- It runs every day at 08:45 IST.
- It also supports manual runs from the Actions tab.
- It writes a `.env` file from the `ENV_FILE` repository secret.
- It invokes the FastAPI `/run` route, which executes the stock pipeline and sends email notifications.

Required GitHub repository secret:

- `ENV_FILE`: the full contents of your production `.env` file

## Notes

- The NSE site is unofficial for direct API use and can rate-limit or change behavior. This project
  uses retry logic and browser-like headers, but you should expect occasional upstream instability.
- Gemini analysis requires `GEMINI_API_KEY`.
- Email delivery requires SMTP credentials in `.env`.
