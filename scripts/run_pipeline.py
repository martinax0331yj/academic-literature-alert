from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fetch_literature import fallback_items, fetch_open_sources, read_manual_records, write_cache
from render_email import render_html, render_markdown
from score_literature import score_items
from send_email import send_email

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
PUSHED_RECORDS = DATA_DIR / "pushed_records.csv"
CACHE_PATH = DATA_DIR / "literature_cache.jsonl"
PREVIEW_PATH = DATA_DIR / "last_email_preview.md"
LOGGER = logging.getLogger("academic_literature_alert")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run academic literature alert pipeline.")
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--dry-run", action="store_true", help="Generate preview and records without sending email.")
    parser.add_argument("--manual-records", type=Path, help="Optional CSV/XLSX file exported manually by the user.")
    parser.add_argument("--skip-network", action="store_true", help="Use fallback/manual records only.")
    args = parser.parse_args()

    setup_logging()
    ensure_data_files()

    LOGGER.info("Pipeline started: mode=%s dry_run=%s", args.mode, args.dry_run)
    items = []
    if args.manual_records:
        items.extend(read_manual_records(args.manual_records))
    if not args.skip_network:
        items.extend(fetch_open_sources(args.mode))
    if not items:
        LOGGER.warning("No open-source records fetched; using metadata-only fallback seeds.")
        items = fallback_items(args.mode)

    write_cache(items, CACHE_PATH)
    scored = score_items(items)
    selected = select_items(scored, args.mode)
    records = load_records(PUSHED_RECORDS)
    fresh = filter_recent_duplicates(selected, records, args.mode)
    record_items = fresh
    if not fresh:
        LOGGER.info("All selected items were recently pushed; keeping a preview from selected items.")
        fresh = selected[: min(len(selected), target_count(args.mode))]

    markdown = render_markdown(fresh, args.mode)
    html = render_html(fresh, args.mode)
    PREVIEW_PATH.write_text(markdown, encoding="utf-8")
    subject = f"[Literature Alert] {args.mode} digest - {date.today().isoformat()}"
    sent = send_email(subject, markdown, html, dry_run=args.dry_run)
    append_records(record_items, PUSHED_RECORDS, status="sent" if sent else "preview")
    LOGGER.info("Pipeline finished: selected=%s fresh=%s recorded=%s sent=%s", len(selected), len(fresh), len(record_items), sent)


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "pipeline.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def ensure_data_files() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PUSHED_RECORDS.exists():
        PUSHED_RECORDS.write_text("doi,title_hash,title,category,first_seen_date,pushed_date,source,status\n", encoding="utf-8")
    if not CACHE_PATH.exists():
        CACHE_PATH.write_text("", encoding="utf-8")


def select_items(items: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    sorted_items = sorted(items, key=lambda item: int(item.get("score", 0)), reverse=True)
    if mode == "weekly":
        return balanced_weekly(sorted_items)
    return balanced_daily(sorted_items)


def balanced_daily(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = {
        "classic_highly_cited_english": lambda item: item.get("language") == "en" and (item.get("citation_count") or 0) >= 50,
        "transferable_management_communication": lambda item: item.get("matched_category") == "transferable_management_communication",
        "technology_frontier": lambda item: item.get("matched_category") == "technology_frontier" or item.get("category") == "technology_frontier",
        "digital_publishing_frontier": lambda item: item.get("matched_category") == "digital_publishing" or item.get("category") == "digital_publishing",
    }
    selected: list[dict[str, Any]] = []
    seen = set()
    for bucket, predicate in buckets.items():
        matches = [item for item in items if predicate(item)]
        for item in matches[:2]:
            key = item_key(item)
            if key not in seen:
                enriched = dict(item)
                enriched["daily_bucket"] = bucket
                selected.append(enriched)
                seen.add(key)
    for item in items:
        if len(selected) >= 8:
            break
        key = item_key(item)
        if key not in seen:
            selected.append(item)
            seen.add(key)
    return selected[:8]


def balanced_weekly(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    zh = [item for item in items if item.get("language") == "zh"]
    en = [item for item in items if item.get("language") != "zh"]
    selected = zh[:2] + en[:2]
    seen = {item_key(item) for item in selected}
    for item in items:
        if len(selected) >= 4:
            break
        key = item_key(item)
        if key not in seen:
            selected.append(item)
            seen.add(key)
    return selected[:4]


def target_count(mode: str) -> int:
    return 4 if mode == "weekly" else 8


def load_records(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def filter_recent_duplicates(items: list[dict[str, Any]], records: list[dict[str, str]], mode: str) -> list[dict[str, Any]]:
    today = date.today()
    recent_keys: set[str] = set()
    for record in records:
        pushed_date = parse_date(record.get("pushed_date", ""))
        if not pushed_date:
            continue
        days = (today - pushed_date).days
        limit = 180 if record.get("category") == "classic_highly_cited_english" or mode == "daily" and "classic" in record.get("category", "") else 90
        if days <= limit:
            recent_keys.add(record.get("doi") or record.get("title_hash") or "")
    fresh = []
    for item in items:
        if item_key(item) not in recent_keys:
            fresh.append(item)
    return fresh


def append_records(items: list[dict[str, Any]], path: Path, status: str) -> None:
    existing = load_records(path)
    first_seen = {(row.get("doi") or row.get("title_hash")): row.get("first_seen_date") for row in existing}
    today = date.today().isoformat()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doi", "title_hash", "title", "category", "first_seen_date", "pushed_date", "source", "status"])
        for item in items:
            key = item_key(item)
            writer.writerow(
                {
                    "doi": normalize_doi(str(item.get("doi", ""))),
                    "title_hash": title_hash(str(item.get("title", ""))),
                    "title": item.get("title", ""),
                    "category": item.get("daily_bucket") or item.get("category") or item.get("matched_category") or "uncategorized",
                    "first_seen_date": first_seen.get(key, today),
                    "pushed_date": today,
                    "source": item.get("source", "missing"),
                    "status": status,
                }
            )


def item_key(item: dict[str, Any]) -> str:
    doi = normalize_doi(str(item.get("doi", "")))
    if doi:
        return doi
    return title_hash(str(item.get("title", "")))


def normalize_doi(doi: str) -> str:
    return doi.strip().lower().replace("https://doi.org/", "")


def normalize_title(title: str) -> str:
    lowered = title.casefold().strip()
    return re.sub(r"\W+", "", lowered)


def title_hash(title: str) -> str:
    return hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()[:16]


def parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
