from __future__ import annotations

import json
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


BOB_URL = "https://www.bankofbaroda.in/career/current-opportunities"


def extract_master_career_details(html: str) -> list[dict]:
    """
    Extract:
        var glblMasterCareerDetails = [...];
    from the BOB careers page source.
    """
    pattern = re.compile(
        r"var\s+glblMasterCareerDetails\s*=\s*(\[.*?\])\s*;",
        flags=re.S,
    )

    match = pattern.search(html)

    if not match:
        raise ValueError(
            "glblMasterCareerDetails was not found in BOB page source"
        )

    return json.loads(match.group(1))


def extract_apply_url(ap_cta: str) -> str | None:
    """
    Extract the actual application URL from the apCta HTML.

    Example:
        <a class='bob-comman-btn'
           href='https://example.com/apply'>
            Apply Now
        </a>
    """
    if not ap_cta:
        return None

    soup = BeautifulSoup(ap_cta, "html.parser")
    anchor = soup.select_one("a[href]")

    if not anchor:
        return None

    href = (anchor.get("href") or "").strip()

    if not href:
        return None

    return absolute_url(BOB_URL, href)


def get_detail_pdf(detail_url: str) -> str | None:
    """
    Fetch the BOB detail page referenced by `cta` and extract the
    advertisement PDF from `.eauction-details-div.b-0`.
    """
    response = fetch(detail_url, timeout=30)
    soup = BeautifulSoup(response.text, "html.parser")

    container = soup.select_one(".eauction-details-div.b-0")

    if not container:
        return None

    # Prefer an actual PDF link instead of taking the first arbitrary anchor.
    for anchor in container.select("a[href]"):
        href = (anchor.get("href") or "").strip()

        if not href:
            continue

        clean_href = href.lower().split("?", 1)[0]

        if clean_href.endswith(".pdf"):
            return absolute_url(detail_url, href)

    return None


def parse_bob_job(item: dict, kw: dict) -> dict | None:
    title = normalize(item.get("prfile", ""))
    advertisement_no = normalize(item.get("Advtno", ""))

    # cta points to the BOB detail page containing the PDF descriptor.
    detail_url = normalize(item.get("cta", ""))

    # apCta contains the actual Apply Now link.
    apply_url = extract_apply_url(item.get("apCta", ""))

    # A usable record needs both the application URL and detail page URL.
    if not apply_url or not detail_url:
        return None

    try:
        advertisement_url = get_detail_pdf(detail_url)
    except Exception as exc:
        return {
            "id": stable_id(
                "BOB",
                advertisement_no or title,
                detail_url,
            ),
            "source": "Bank of Baroda",
            "title": title,
            "advertisement_no": advertisement_no,
            "apply_url": apply_url,
            "url": detail_url,
            "fit": "parse-error",
            "include_hits": [],
            "exclude_hits": [],
            "senior_hits": [],
            "error": f"Could not parse BOB detail page: {exc}",
        }

    if not advertisement_url:
        return {
            "id": stable_id(
                "BOB",
                advertisement_no or title,
                detail_url,
            ),
            "source": "Bank of Baroda",
            "title": title,
            "advertisement_no": advertisement_no,
            "apply_url": apply_url,
            "url": detail_url,
            "advertisement_url": None,
            "fit": "verification-incomplete",
            "include_hits": [],
            "exclude_hits": [],
            "senior_hits": [],
            "error": (
                "No advertisement PDF found inside "
                ".eauction-details-div.b-0"
            ),
        }

    try:
        pdf_response = fetch(advertisement_url, timeout=45)
        pdf_text = extract_pdf_text(
            pdf_response.content,
            max_pages=12,
        )
    except Exception as exc:
        return {
            "id": stable_id(
                "BOB",
                advertisement_no or title,
                advertisement_url,
            ),
            "source": "Bank of Baroda",
            "title": title,
            "advertisement_no": advertisement_no,
            "apply_url": apply_url,
            "advertisement_url": advertisement_url,
            "url": detail_url,
            "fit": "parse-error",
            "include_hits": [],
            "exclude_hits": [],
            "senior_hits": [],
            "error": f"Could not parse BOB PDF: {exc}",
        }

    metadata_text = "\n".join(
        [
            title,
            advertisement_no,
            normalize(item.get("fntn", "")),
            normalize(item.get("multiplefunction", "")),
            normalize(item.get("city", "")),
            normalize(item.get("exprn", "")),
            normalize(item.get("vacan", "")),
            normalize(item.get("latestUpdate", "")),
            pdf_text,
        ]
    )

    scored = score_job(title, metadata_text, kw)

    if scored["fit"] == "ignore":
        return None

    return {
        "id": stable_id(
            "BOB",
            advertisement_no or title,
            advertisement_url,
        ),
        "source": "Bank of Baroda",
        "title": title,
        "function": normalize(item.get("fntn", "")),
        "location": normalize(item.get("city", "")),
        "experience": normalize(item.get("exprn", "")),
        "vacancies": normalize(item.get("vacan", "")),
        "advertisement_no": advertisement_no,
        "start_date": item.get("eDate"),
        "last_date": item.get("lDate"),
        "latest_update": normalize(item.get("latestUpdate", "")),
        "apply_url": apply_url,
        "advertisement_url": advertisement_url,
        "url": detail_url,
        "fit": scored["fit"],
        "include_hits": scored["include_hits"],
        "exclude_hits": scored["exclude_hits"],
        "senior_hits": scored["senior_hits"],
    }


def scrape_bob(kw: dict) -> dict:
    result = {
        "source": "Bank of Baroda",
        "url": BOB_URL,
        "jobs": [],
        "errors": [],
        "stats": {
            "records_found": 0,
            "records_with_apply_url": 0,
            "advertisement_pdfs_found": 0,
            "matched_jobs": 0,
        },
    }

    try:
        response = fetch(BOB_URL, timeout=30)
        records = extract_master_career_details(response.text)
    except Exception as exc:
        result["errors"].append(
            f"BOB careers data extraction failed: {exc}"
        )
        return result

    result["stats"]["records_found"] = len(records)

    jobs = []

    for item in records:
        # FIX: apCta contains the Apply Now anchor.
        # cta is only the detail-page URL.
        apply_url = extract_apply_url(item.get("apCta", ""))

        if not apply_url:
            continue

        detail_url = normalize(item.get("cta", ""))

        if not detail_url:
            continue

        # breakpoint()
        result["stats"]["records_with_apply_url"] += 1

        job = parse_bob_job(item, kw)

        if not job:
            continue

        if job.get("advertisement_url"):
            result["stats"]["advertisement_pdfs_found"] += 1

        jobs.append(job)

    jobs = list(
        {
            job["id"]: job
            for job in jobs
        }.values()
    )

    result["jobs"] = jobs
    result["stats"]["matched_jobs"] = len(jobs)

    return result