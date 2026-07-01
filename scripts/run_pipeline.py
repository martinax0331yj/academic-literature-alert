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

try:
    import yaml
except ImportError:  # pragma: no cover - local fallback for minimal environments
    yaml = None

from fetch_literature import fallback_items, fetch_open_sources, get_discovery_stats, read_manual_records, write_cache
from render_email import render_html, render_markdown
from score_literature import score_items
from send_email import send_email

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
PUSHED_RECORDS = DATA_DIR / "pushed_records.csv"
CACHE_PATH = DATA_DIR / "literature_cache.jsonl"
PREVIEW_PATH = DATA_DIR / "last_email_preview.md"
SCHEDULES_PATH = ROOT / "config" / "schedules.yml"
LOGGER = logging.getLogger("academic_literature_alert")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run academic literature alert pipeline.")
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--dry-run", action="store_true", help="Generate preview without sending email or updating pushed records.")
    parser.add_argument("--manual-records", type=Path, help="Optional CSV/XLSX file exported manually by the user.")
    parser.add_argument("--skip-network", action="store_true", help="Use fallback/manual records only.")
    args = parser.parse_args()

    setup_logging()
    ensure_data_files()
    send_empty_digest = should_send_empty_digest(args.mode)

    LOGGER.info("Pipeline started: mode=%s dry_run=%s", args.mode, args.dry_run)
    items = []
    if args.manual_records:
        items.extend(read_manual_records(args.manual_records))
    if not args.skip_network:
        items.extend(fetch_open_sources(args.mode))
    discovery_stats = get_discovery_stats()
    if not items:
        LOGGER.warning("No open-source records fetched; using metadata-only fallback seeds.")
        items = fallback_items(args.mode)

    for item in items:
        item["alert_mode"] = args.mode
    write_cache(items, CACHE_PATH)
    scored = score_items(items)
    selected = select_items(scored, args.mode)
    filtered_reasons = top_filtered_records(items, scored)
    records = load_records(PUSHED_RECORDS)
    fresh = filter_recent_duplicates(selected, records, args.mode)
    record_items = fresh
    preview_only = False
    if not fresh:
        if selected:
            LOGGER.info("All selected items were recently pushed.")
        else:
            LOGGER.info("No items passed the quality gate.")
        if send_empty_digest:
            LOGGER.info("Empty digest enabled for mode=%s.", args.mode)
            fresh = []
        elif args.dry_run:
            LOGGER.info("Dry-run preview will show selected duplicate candidates for inspection.")
            fresh = selected[: min(len(selected), target_count(args.mode))]
            preview_only = True
        else:
            fresh = []
            preview_only = True

    diagnostics = build_diagnostics(discovery_stats, len(items), len(fresh), filtered_reasons)
    log_diagnostics(diagnostics)
    markdown = render_markdown(fresh, args.mode, preview_only=preview_only)
    if not fresh:
        markdown = append_diagnostics_to_preview(markdown, diagnostics)
    html = render_html(fresh, args.mode, preview_only=preview_only)
    PREVIEW_PATH.write_text(markdown, encoding="utf-8")
    subject = email_subject(args.mode, has_items=bool(fresh))
    sent = False
    should_send = (bool(fresh) or send_empty_digest) and not preview_only
    if should_send:
        sent = send_email(subject, markdown, html, dry_run=args.dry_run)
    elif args.dry_run:
        send_email(subject, markdown, html, dry_run=True)
    else:
        LOGGER.info("No fresh items; email was not sent.")
    if args.dry_run:
        LOGGER.info("Dry-run enabled; pushed records were not updated.")
    elif sent:
        append_records(record_items, PUSHED_RECORDS, status="sent")
    else:
        LOGGER.warning("Email was not sent; pushed records were not updated.")
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


def should_send_empty_digest(mode: str) -> bool:
    fallback = mode == "weekly"
    if yaml is None or not SCHEDULES_PATH.exists():
        return fallback
    with SCHEDULES_PATH.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    return bool(config.get(mode, {}).get("send_empty_digest", fallback))


def email_subject(mode: str, has_items: bool) -> str:
    if mode == "weekly":
        if has_items:
            return "【文献推送｜每周精选】核心/高质量期刊论文精选"
        return "【文献推送｜每周精选】本周暂无符合条件的高质量期刊论文"
    return f"[Literature Alert] {mode} digest - {date.today().isoformat()}"


def select_items(items: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    eligible_items = [
        item for item in items
        if item.get("eligible_for_email") and item.get("priority") in {"A", "B"}
    ]
    sorted_items = sorted(eligible_items, key=lambda item: int(item.get("score", 0)), reverse=True)
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


def build_diagnostics(
    discovery_stats: dict[str, int],
    candidate_total: int,
    final_count: int,
    filtered_reasons: list[dict[str, str]],
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = dict(discovery_stats)
    diagnostics["candidate_total_before_filter"] = candidate_total
    diagnostics["final_email_record_count"] = final_count
    diagnostics["top_filtered_records"] = filtered_reasons
    return diagnostics


def log_diagnostics(diagnostics: dict[str, Any]) -> None:
    for key in [
        "loaded_journal_zh_count",
        "loaded_journal_en_count",
        "journal_whitelist_discovery_count",
        "fetched_from_openalex_journal_count",
        "fetched_from_semantic_scholar_count",
        "candidate_total_before_filter",
        "final_email_record_count",
    ]:
        LOGGER.info("%s=%s", key, diagnostics.get(key, 0))
    for item in diagnostics.get("top_filtered_records", [])[:5]:
        LOGGER.info("filtered_record title=%r reason=%s", item.get("title"), item.get("reason"))


def top_filtered_records(items: list[dict[str, Any]], scored: list[dict[str, Any]]) -> list[dict[str, str]]:
    selected_keys = {item_key(item) for item in scored}
    filtered: list[dict[str, str]] = []
    for item in items:
        key = item_key(item)
        if key in selected_keys:
            continue
        filtered.append({"title": str(item.get("title", "missing")), "reason": filter_reason(item)})
        if len(filtered) >= 8:
            break
    return filtered


def filter_reason(item: dict[str, Any]) -> str:
    if item.get("source") == "fallback_seed":
        return "fallback metadata is not eligible"
    if item.get("is_crossref_only") or str(item.get("source", "")).casefold() == "crossref":
        return "crossref-only or metadata-only source"
    if missing_value(item.get("venue")):
        return "missing journal/source"
    if is_future_item(item):
        return "future publication year"
    work_type = str(item.get("work_type", "")).casefold()
    if work_type in {"book", "book-chapter", "chapter", "component", "monograph", "proceedings", "proceedings-article"}:
        return f"blocked work_type={work_type}"
    if missing_value(item.get("abstract")):
        return "missing abstract"
    return "did not pass topic relevance, priority, or score threshold"


def append_diagnostics_to_preview(markdown: str, diagnostics: dict[str, Any]) -> str:
    lines = [
        markdown.rstrip(),
        "",
        "## 诊断摘要",
        "",
        f"- loaded_journal_zh_count: {diagnostics.get('loaded_journal_zh_count', 0)}",
        f"- loaded_journal_en_count: {diagnostics.get('loaded_journal_en_count', 0)}",
        f"- journal_whitelist_discovery_count: {diagnostics.get('journal_whitelist_discovery_count', 0)}",
        f"- fetched_from_openalex_journal_count: {diagnostics.get('fetched_from_openalex_journal_count', 0)}",
        f"- fetched_from_semantic_scholar_count: {diagnostics.get('fetched_from_semantic_scholar_count', 0)}",
        f"- candidate_total_before_filter: {diagnostics.get('candidate_total_before_filter', 0)}",
        f"- final_email_record_count: {diagnostics.get('final_email_record_count', 0)}",
        "",
        "### Top Filtered Records",
        "",
    ]
    filtered = diagnostics.get("top_filtered_records", [])
    if filtered:
        for item in filtered[:5]:
            lines.append(f"- {item.get('title', 'missing')}: {item.get('reason', 'unknown')}")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def missing_value(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().casefold()
    return not text or text in {"missing", "none", "null", "nan", "未获取"}


def is_future_item(item: dict[str, Any]) -> bool:
    year = re.search(r"(19|20)\d{2}", str(item.get("published_date") or item.get("year") or ""))
    return bool(year and int(year.group(0)) > date.today().year)


def load_records(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def filter_recent_duplicates(items: list[dict[str, Any]], records: list[dict[str, str]], mode: str) -> list[dict[str, Any]]:
    today = date.today()
    recent_dois: set[str] = set()
    recent_title_hashes: set[str] = set()
    for record in records:
        if record.get("status") != "sent":
            continue
        pushed_date = parse_date(record.get("pushed_date", ""))
        if not pushed_date:
            continue
        days = (today - pushed_date).days
        limit = 180 if is_classic_record(record) else 90
        if days <= limit:
            doi = normalize_doi(record.get("doi", ""))
            title = record.get("title_hash", "")
            if doi:
                recent_dois.add(doi)
            if title:
                recent_title_hashes.add(title)
    fresh = []
    for item in items:
        doi = normalize_doi(str(item.get("doi", "")))
        title = title_hash(str(item.get("title", "")))
        if doi and doi in recent_dois:
            continue
        if title and title in recent_title_hashes:
            continue
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
                    "category": record_category(item),
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
    return doi.strip().lower().replace("https://doi.org/", "").replace("http://doi.org/", "")


def record_category(item: dict[str, Any]) -> str:
    if is_classic_item(item):
        return "classic_highly_cited_english"
    return item.get("daily_bucket") or item.get("category") or item.get("matched_category") or "uncategorized"


def is_classic_item(item: dict[str, Any]) -> bool:
    try:
        citations = int(item.get("citation_count") or 0)
    except (TypeError, ValueError):
        citations = 0
    return item.get("language") == "en" and citations >= 50


def is_classic_record(record: dict[str, str]) -> bool:
    return "classic" in (record.get("category") or "")


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
