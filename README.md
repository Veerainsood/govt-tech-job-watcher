# Bank Tech Job Watcher
[![Bank Tech Job Watcher](https://github.com/Veerainsood/govt-tech-job-watcher/actions/workflows/workflow.yml/badge.svg?branch=main)](https://github.com/Veerainsood/govt-tech-job-watcher/actions/workflows/workflow.yml)

Tracks bank/regulator career pages for technical openings and sends alerts.

## First targets
- SBI
- RBI
- Bank of Baroda

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scrapers/main.py
```

## Telegram alerts

Add GitHub secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

The GitHub Action runs every 3 hours and updates `data/jobs.json`.
