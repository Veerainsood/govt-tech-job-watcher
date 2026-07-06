from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import fitz
import requests
import yaml
from bs4 import BeautifulSoup

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
KEYWORDS_FILE = ROOT / "keywords.yml"
USER_AGENT = "bank-tech-job-watcher/0.1"

def load_yaml(path: Path = KEYWORDS_FILE) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))

def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch(url: str, timeout: int = 30) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    return r

def absolute_url(base_url: str, href: str) -> str:
    return requests.compat.urljoin(base_url, href)

def extract_pdf_text(pdf_bytes: bytes, max_pages: int = 8) -> str:
    text_parts = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc[:max_pages]:
            text_parts.append(page.get_text("text"))
    return "\n".join(text_parts)

def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]

def score_job(title: str, text: str, kw: dict) -> dict:
    hay = f"{title}\n{text}".lower()
    include_hits = [k for k in kw["include"] if k.lower() in hay]
    exclude_hits = [k for k in kw["exclude"] if k.lower() in hay]
    senior_hits = [k for k in kw.get("senior_markers", []) if k.lower() in hay]

    relevant = bool(include_hits) and not exclude_hits
    fit = "good-fit" if relevant and not senior_hits else "senior/not-fit" if include_hits and senior_hits else "ignore"

    return {
        "fit": fit,
        "include_hits": include_hits,
        "exclude_hits": exclude_hits,
        "senior_hits": senior_hits,
    }

def send_telegram(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    # breakpoint()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": message, "disable_web_page_preview": False}, timeout=20)
