from __future__ import annotations

from datetime import datetime, timezone
import traceback

from scrapers.common import DATA_DIR, load_json, load_yaml, save_json, send_telegram
from scrapers.sbi import scrape_sbi
from scrapers.bob import scrape_bob


def run_scraper_safe(scraper, keywords: dict) -> list[dict]:
    try:
        return scraper(keywords)
    except Exception as e:
        return {
            "source": getattr(scraper, "__name__", "unknown"),
            "url": None,
            "jobs": [],
            "errors": [f"{getattr(scraper, '__name__', 'unknown')} crashed: {e}"],
            "stats": {},
        }


def main():
    keywords = load_yaml()

    seen_path = DATA_DIR / "seen.json"
    seen_errors_path = DATA_DIR / "seen_errors.json"
    jobs_path = DATA_DIR / "jobs.json"
    errors_path = DATA_DIR / "errors.json"
    scraper_results_path = DATA_DIR / "scraper_results.json"

    seen = set(load_json(seen_path, []))
    seen_errors = set(load_json(seen_errors_path, []))

    all_jobs = []
    errors = []
    scraper_results = []

    for scraper in [scrape_sbi,scrape_bob]:
        result = run_scraper_safe(scraper, keywords)

        scraper_results.append(result)

        # collect jobs
        all_jobs.extend(result.get("jobs", []))

        # collect scraper/site errors
        for err in result.get("errors", []):
            errors.append({
                "source": result.get("source", scraper.__name__),
                "url": result.get("url"),
                "error": err,
                "stats": result.get("stats", {}),
            })

    new_relevant = []

    for job in all_jobs:
        job_id = job.get("id")

        if not job_id:
            continue

        if job_id not in seen:
            seen.add(job_id)

            # Only alert actually relevant jobs.
            if job.get("fit") == "good-fit":
                new_relevant.append(job)

    now = datetime.now(timezone.utc).isoformat()

    save_json(jobs_path, {
        "updated_at": now,
        "count": len(all_jobs),
        "good_fit_count": len([j for j in all_jobs if j.get("fit") == "good-fit"]),
        "jobs": all_jobs,
    })

    save_json(errors_path, {
        "updated_at": now,
        "count": len(errors),
        "errors": errors,
    })

    save_json(scraper_results_path, {
        "updated_at": now,
        "results": scraper_results,
    })

    save_json(seen_path, sorted(seen))

    for job in new_relevant:
        send_telegram(
            "✅ New bank tech opening matched\n\n"
            f"Source: {job.get('source')}\n"
            f"Title: {job.get('title')}\n"
            f"Fit: {job.get('fit')}\n"
            f"Last date: {job.get('last_date')}\n"
            f"Matched: {', '.join(job.get('include_hits', []))}\n\n"
            f"Apply: {job.get('apply_url')}\n"
            f"Ad: {job.get('advertisement_url')}"
        )

    new_errors = []

    for err in errors:
        error_id = f"{err.get('source')}::{err.get('error')}"

        if error_id not in seen_errors:
            seen_errors.add(error_id)
            new_errors.append(err)

    for err in new_errors:
        send_telegram(
            "⚠️ Bank job scraper issue\n\n"
            f"Source: {err.get('source')}\n"
            f"URL: {err.get('url')}\n"
            f"Error: {err.get('error')}\n"
            f"Stats: {err.get('stats')}\n\n"
            "Parser/site may have changed. Check GitHub Actions logs."
        )

    save_json(seen_errors_path, sorted(seen_errors))

    print(
        f"Found {len(all_jobs)} matched/non-ignored jobs. "
        f"Good-fit total: {len([j for j in all_jobs if j.get('fit') == 'good-fit'])}. "
        f"New good-fit alerts: {len(new_relevant)}. "
        f"Errors: {len(errors)}."
    )


if __name__ == "__main__":
    main()

