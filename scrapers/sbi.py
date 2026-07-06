from __future__ import annotations

import re

from bs4 import BeautifulSoup

from scrapers.common import (
    absolute_url,
    extract_pdf_text,
    fetch,
    normalize,
    score_job,
    stable_id,
)


SBI_URL = "https://sbi.bank.in/web/careers/current-openings"
SBI_ORIGIN = "https://sbi.bank.in"


def sbi_url(href: str | None) -> str | None:
    """
    SBI often gives href like /documents/...
    Join with site origin, not the current page path.
    """
    if not href:
        return None

    href = href.strip()

    if not href:
        return None

    return absolute_url(SBI_ORIGIN, href)


def text_of(el) -> str:
    if not el:
        return ""
    return normalize(el.get_text(" ", strip=True))


def get_apply_url(card) -> str | None:
    """
    Active openings usually have visible Apply Now / Apply Online.
    Old apply links may be commented out, which BeautifulSoup ignores.
    """
    for a in card.select("a[href]"):
        text = text_of(a).lower()
        classes = " ".join(a.get("class", [])).lower()
        href = a.get("href")

        if (
            "apply-now-btn" in classes
            or "apply now" in text
            or "apply online" in text
        ):
            return sbi_url(href)

    return None


def get_title(card) -> str:
    """
    Prefer the main recruitment text inside the SBI card.
    Example:
    RECRUITMENT OF SPECIALIST CADRE OFFICER ON REGULAR BASIS...
    """
    selectors = [
        ".col-md-8 p",
        ".col-lg-8 p",
        ".col-xl-8 p",
        ".card-title",
        "h3",
        "h4",
        "h5",
        "p",
    ]

    for selector in selectors:
        el = card.select_one(selector)
        txt = text_of(el)

        if txt and "advertisement no" not in txt.lower():
            return txt

    return text_of(card)[:160]


def extract_advertisement_no(text: str) -> str | None:
    patterns = [
        r"ADVERTISEMENT\s+NO\.?\s*:?\s*([A-Z0-9/_\-.]+)",
        r"ADVT\.?\s+NO\.?\s*:?\s*([A-Z0-9/_\-.]+)",
        r"(CRPD/[A-Z0-9/_\-.]+)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            return normalize(m.group(1))

    return None


def extract_apply_window(text: str) -> dict:
    """
    Extracts Apply Online from DD.MM.YYYY to DD.MM.YYYY if present.
    """
    m = re.search(
        r"apply\s+online\s+from\s+"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})"
        r"\s*(?:to|-)\s*"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        text,
        flags=re.I,
    )

    if not m:
        return {"start_date": None, "last_date": None}

    return {
        "start_date": m.group(1),
        "last_date": m.group(2),
    }


def find_advertisement_block(card):
    """
    Find the block containing DOWNLOAD ADVERTISEMENT.
    """
    for el in card.find_all(["li", "div", "p", "span"]):
        txt = text_of(el).lower()
        if "download advertisement" in txt or "advertisement" in txt:
            if el.select_one("a[href]"):
                return el

    return None


def pick_advertisement_pdf(card) -> str | None:
    """
    Prefer PDF links near DOWNLOAD ADVERTISEMENT.
    Fallback: first PDF inside card.
    """
    ad_block = find_advertisement_block(card)

    search_root = ad_block if ad_block else card

    pdfs = []

    for a in search_root.select("a[href]"):
        href = a.get("href", "")
        label = text_of(a).lower()

        if ".pdf" not in href.lower():
            continue

        pdfs.append((label, sbi_url(href)))

    if not pdfs:
        return None

    preferred_words = [
        "english",
        "detailed",
        "final",
        "advertisement",
        "adv",
    ]

    for label, url in pdfs:
        if any(w in label for w in preferred_words):
            return url

    return pdfs[0][1]


def should_download_pdf(card_text: str, kw: dict) -> bool:
    """
    Decide from full visible card text, not only classes/data attributes.

    This catches:
    RECRUITMENT OF SPECIALIST CADRE OFFICER...
    ASSISTANT MANAGER SYSTEM...
    INFORMATION TECHNOLOGY...
    SOFTWARE...
    """
    scored = score_job("", card_text, kw)

    if scored["include_hits"] and not scored["exclude_hits"]:
        return True

    fallback_terms = [
        "system",
        "systems",
        "software",
        "developer",
        "technology",
        "information technology",
        "it ",
        "cyber",
        "security",
        "cloud",
        "data",
        "database",
        "network",
        "ai",
        "ml",
        "analytics",
        "assistant manager",
        "deputy manager",
        "specialist cadre officer",
        "sco",
    ]

    hay = card_text.lower()

    return any(term in hay for term in fallback_terms)


def parse_card(card, kw: dict):
    """
    Returns:
      (job_dict | None, ad_pdf_found: bool)

    Important:
    - It scores the whole visible card text.
    - Active alerts require visible Apply Now / Apply Online.
    - PDF parsing is only attempted when card text looks possibly relevant.
    """
    card_text = text_of(card)
    title = get_title(card)

    role = normalize(card.get("data-type-role", "") or "")
    location = normalize(card.get("data-type-location", "") or "")
    article_id = normalize(card.get("data-articleid", "") or "")

    adv_no = extract_advertisement_no(card_text) or article_id
    dates = extract_apply_window(card_text)

    apply_url = get_apply_url(card)
    # breakpoint()
    # Active alerts only.
    if not apply_url:
        return None, False

    ad_pdf_url = pick_advertisement_pdf(card)

    if not ad_pdf_url:
        return None, False

    pdf_text = ""

    if should_download_pdf(card_text, kw):
        try:
            pdf_resp = fetch(ad_pdf_url, timeout=45)
            pdf_text = extract_pdf_text(pdf_resp.content, max_pages=8)
        except Exception as e:
            # Return an error job because this is useful for scraper monitoring.
            return {
                "id": stable_id("SBI", adv_no or title, ad_pdf_url),
                "source": "SBI",
                "title": title,
                "role": role,
                "location": location,
                "advertisement_no": adv_no,
                "start_date": dates["start_date"],
                "last_date": dates["last_date"],
                "apply_url": apply_url,
                "advertisement_url": ad_pdf_url,
                "url": SBI_URL,
                "fit": "parse-error",
                "include_hits": [],
                "exclude_hits": [],
                "senior_hits": [],
                "error": f"Could not parse SBI advertisement PDF: {e}",
            }, True

    full_text = "\n".join(
        [
            title,
            role,
            location,
            adv_no or "",
            card_text,
            pdf_text,
        ]
    )

    scored = score_job(title, full_text, kw)

    if scored["fit"] == "ignore":
        return None, True

    return {
        "id": stable_id("SBI", adv_no or title, ad_pdf_url),
        "source": "SBI",
        "title": title,
        "role": role,
        "location": location,
        "advertisement_no": adv_no,
        "start_date": dates["start_date"],
        "last_date": dates["last_date"],
        "apply_url": apply_url,
        "advertisement_url": ad_pdf_url,
        "url": SBI_URL,
        "fit": scored["fit"],
        "include_hits": scored["include_hits"],
        "exclude_hits": scored["exclude_hits"],
        "senior_hits": scored["senior_hits"],
    }, True


def dedupe_jobs(jobs: list[dict]) -> list[dict]:
    seen = set()
    out = []

    for job in jobs:
        key = job.get("id") or (
            job.get("source"),
            job.get("advertisement_no"),
            job.get("title"),
            job.get("advertisement_url"),
        )

        if key in seen:
            continue

        seen.add(key)
        out.append(job)

    return out


def scrape_sbi(kw: dict) -> dict:
    result = {
        "source": "SBI",
        "url": SBI_URL,
        "jobs": [],
        "errors": [],
        "stats": {
            "cards_found": 0,
            "active_cards_found": 0,
            "advertisement_pdfs_found": 0,
            "matched_jobs": 0,
        },
    }

    try:
        resp = fetch(SBI_URL, timeout=30)
    except Exception as e:
        result["errors"].append(f"SBI careers page fetch failed: {e}")
        return result

    soup = BeautifulSoup(resp.text, "html.parser")

    cards = soup.select("#jobLinks .card")

    if not cards:
        cards = soup.select(".card")

    result["stats"]["cards_found"] = len(cards)

    if not cards:
        result["errors"].append("No SBI job cards found. SBI page structure may have changed.")
        return result

    jobs = []

    for card in cards:
        if get_apply_url(card):
            result["stats"]["active_cards_found"] += 1

        job, ad_pdf_found = parse_card(card, kw)

        if ad_pdf_found:
            result["stats"]["advertisement_pdfs_found"] += 1

        if job:
            jobs.append(job)

    jobs = dedupe_jobs(jobs)

    result["jobs"] = jobs
    result["stats"]["matched_jobs"] = len(jobs)

    if (
        result["stats"]["active_cards_found"] > 0
        and result["stats"]["advertisement_pdfs_found"] == 0
    ):
        result["errors"].append(
            "SBI active cards were found, but no advertisement PDFs were found. "
            "Advertisement link structure may have changed."
        )
    return result