from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from journal_config import load_yaml_file

try:
    import yaml
except ImportError:  # pragma: no cover - local fallback for minimal environments
    yaml = None

from fetch_literature import fallback_items, fetch_open_sources, get_discovery_stats, read_manual_records, write_cache
from render_email import render_html, render_html_from_markdown, render_markdown
from score_literature import load_exclusion_rules, load_journal_names, load_topic_groups, score_item, score_items
from send_email import send_email

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
PUSHED_RECORDS = DATA_DIR / "pushed_records.csv"
CACHE_PATH = DATA_DIR / "literature_cache.jsonl"
PREVIEW_PATH = DATA_DIR / "last_email_preview.md"
PIPELINE_STATE_PATH = DATA_DIR / "pipeline_state.json"
SCHEDULES_PATH = ROOT / "config" / "schedules.yml"
LOGGER = logging.getLogger("academic_literature_alert")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run academic literature alert pipeline.")
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--dry-run", action="store_true", help="Generate preview without sending email or updating pushed records.")
    parser.add_argument("--email-smoke-test", action="store_true", help="Send a test email only; do not fetch literature or update records.")
    parser.add_argument("--manual-records", type=Path, help="Optional CSV/XLSX file exported manually by the user.")
    parser.add_argument("--skip-network", action="store_true", help="Use fallback/manual records only.")
    args = parser.parse_args()

    setup_logging()
    ensure_data_files()
    current_run_started_at = datetime.now(UTC)
    schedule = schedule_config(args.mode)
    send_empty_digest = should_send_empty_digest(args.mode, schedule)
    time_window = discovery_time_window(args.mode, schedule, current_run_started_at)
    per_query = int(schedule.get("per_query", 8 if args.mode == "daily" else 8) or 8)
    target_records_config = int(schedule.get("target_records", 10 if args.mode == "daily" else 4) or 10)
    max_records_config = int(schedule.get("max_records", 12 if args.mode == "daily" else target_records_config) or target_records_config)

    LOGGER.info("Pipeline started: mode=%s dry_run=%s email_smoke_test=%s", args.mode, args.dry_run, args.email_smoke_test)
    LOGGER.info("mode: %s", args.mode)
    LOGGER.info("dry_run: %s", args.dry_run)
    LOGGER.info("send_empty_digest: %s", send_empty_digest)
    if args.email_smoke_test:
        run_email_smoke_test(args.mode)
        return

    items = []
    if args.manual_records:
        items.extend(read_manual_records(args.manual_records, since_date=time_window["since_date"], until_date=time_window["until_date"]))
    if not args.skip_network:
        items.extend(fetch_open_sources(args.mode, per_query=per_query, since_date=time_window["since_date"], until_date=time_window["until_date"]))
    discovery_stats = get_discovery_stats()
    if not items:
        LOGGER.warning("No open-source records fetched; using metadata-only fallback seeds.")
        items = fallback_items(args.mode)

    for item in items:
        item["alert_mode"] = args.mode
    write_cache(items, CACHE_PATH)
    scored = score_items(items)
    selected = select_items(scored, args.mode, target_records=target_records_config, max_records=max_records_config)
    evaluated = evaluate_items(items)
    block_counts = block_counts_from_evaluated(evaluated)
    filtered_reasons = top_filtered_records(evaluated)
    topic_diagnostics = topic_diagnostics_from_evaluated(evaluated)
    records = load_records(PUSHED_RECORDS)
    fresh = filter_recent_duplicates(selected, records, args.mode)
    duplicate_count = max(0, len(selected) - len(fresh))
    record_items = fresh
    preview_only = False
    if not fresh:
        if selected:
            LOGGER.info("All selected items were recently pushed.")
            if duplicate_count > 0:
                LOGGER.info("records found but all were already pushed")
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
            if args.mode == "daily":
                LOGGER.info("no qualified daily records; email skipped because send_empty_digest=false")
            fresh = []
            preview_only = True

    diagnostics = build_diagnostics(
        discovery_stats,
        len(items),
        len(fresh),
        duplicate_count,
        block_counts,
        filtered_reasons,
        topic_diagnostics,
        selected_diagnostics(fresh),
        time_window,
        args.mode,
        args.dry_run,
        send_empty_digest,
        per_query,
        target_records_config,
        max_records_config,
    )
    log_diagnostics(diagnostics)
    markdown = render_markdown(fresh, args.mode, preview_only=preview_only, diagnostics=diagnostics)
    if not fresh:
        markdown = append_diagnostics_to_preview(markdown, diagnostics)
    html = render_html_from_markdown(markdown)
    PREVIEW_PATH.write_text(markdown, encoding="utf-8")
    subject = email_subject(args.mode, has_items=bool(fresh))
    sent = False
    send_email_called = False
    should_send = (bool(fresh) or send_empty_digest) and not preview_only
    LOGGER.info("should_send_email: %s", should_send)
    if should_send:
        send_email_called = True
        sent = send_email(subject, markdown, html, dry_run=args.dry_run)
    elif args.dry_run:
        send_email_called = True
        send_email(subject, markdown, html, dry_run=True)
    else:
        LOGGER.info("No fresh items; email was not sent.")
    LOGGER.info("send_email_called: %s", send_email_called)
    LOGGER.info("email_sent_successfully: %s", sent)
    if args.dry_run:
        LOGGER.info("Dry-run enabled; pushed records were not updated.")
    elif sent:
        append_records(record_items, PUSHED_RECORDS, status="sent")
        update_pipeline_state(args.mode, current_run_started_at)
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
    if not PIPELINE_STATE_PATH.exists():
        PIPELINE_STATE_PATH.write_text('{"daily": {}, "weekly": {}}\n', encoding="utf-8")


def schedule_config(mode: str) -> dict[str, Any]:
    if not SCHEDULES_PATH.exists():
        return {}
    config = load_yaml_file(SCHEDULES_PATH, yaml)
    return dict(config.get(mode, {}) or {})


def should_send_empty_digest(mode: str, schedule: dict[str, Any] | None = None) -> bool:
    fallback = mode == "weekly"
    schedule = schedule if schedule is not None else schedule_config(mode)
    return bool(schedule.get("send_empty_digest", fallback))


def discovery_time_window(mode: str, schedule: dict[str, Any], current_run_started_at: datetime) -> dict[str, Any]:
    until_at = current_run_started_at
    if mode == "daily":
        state = load_pipeline_state()
        last_successful = str((state.get("daily") or {}).get("last_successful_run_at") or "")
        fallback_days = int(schedule.get("fallback_backfill_days", 90) or 90)
        if last_successful:
            since_at = parse_state_datetime(last_successful) or (until_at - timedelta(days=fallback_days))
            strategy = "last_successful_run"
        else:
            since_at = until_at - timedelta(days=fallback_days)
            strategy = "fallback_backfill_days"
        return {
            "time_window_strategy": strategy,
            "since_date": iso_z(since_at),
            "until_date": iso_z(until_at),
            "fallback_backfill_days": fallback_days,
            "last_successful_run_at": last_successful or "missing",
            "current_run_started_at": iso_z(current_run_started_at),
        }
    lookback_days = int(schedule.get("lookback_days", 180) or 180)
    since_at = until_at - timedelta(days=lookback_days)
    state = load_pipeline_state()
    return {
        "time_window_strategy": "lookback_days",
        "since_date": iso_z(since_at),
        "until_date": iso_z(until_at),
        "fallback_backfill_days": "",
        "last_successful_run_at": str((state.get(mode) or {}).get("last_successful_run_at") or "missing"),
        "current_run_started_at": iso_z(current_run_started_at),
    }


def load_pipeline_state() -> dict[str, Any]:
    if not PIPELINE_STATE_PATH.exists():
        return {"daily": {}, "weekly": {}}
    try:
        return json.loads(PIPELINE_STATE_PATH.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        LOGGER.warning("pipeline_state.json is malformed; treating state as empty.")
        return {"daily": {}, "weekly": {}}


def update_pipeline_state(mode: str, current_run_started_at: datetime) -> None:
    state = load_pipeline_state()
    state.setdefault(mode, {})["last_successful_run_at"] = iso_z(current_run_started_at)
    PIPELINE_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("pipeline_state updated for mode=%s last_successful_run_at=%s", mode, state[mode]["last_successful_run_at"])


def parse_state_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_email_smoke_test(mode: str) -> None:
    subject = "【文献推送测试】Daily email smoke test" if mode == "daily" else "【文献推送测试】Email smoke test"
    markdown = "daily email smoke test passed\n"
    html = "<html><body><p>daily email smoke test passed</p></body></html>"
    LOGGER.info("should_send_email: true")
    LOGGER.info("send_email_called: true")
    try:
        sent = send_email(subject, markdown, html, dry_run=False)
    except Exception:
        LOGGER.info("email_sent_successfully: false")
        raise
    LOGGER.info("email_sent_successfully: %s", sent)


def email_subject(mode: str, has_items: bool) -> str:
    if mode == "weekly":
        if has_items:
            return "【文献推送｜每周精选】核心/高质量期刊论文精选"
        return "【文献推送｜每周精选】本周暂无符合条件的高质量期刊论文"
    return f"[Literature Alert] {mode} digest - {date.today().isoformat()}"


def select_items(items: list[dict[str, Any]], mode: str, target_records: int | None = None, max_records: int | None = None) -> list[dict[str, Any]]:
    eligible_items = [
        item for item in items
        if item.get("eligible_for_email") and item.get("priority") in {"A", "B"}
    ]
    sorted_items = sorted(eligible_items, key=lambda item: int(item.get("score", 0)), reverse=True)
    if mode == "weekly":
        return balanced_weekly(sorted_items, max_records=max_records or 4)
    return balanced_daily(sorted_items, target_records=target_records or 10, max_records=max_records or 12)


def balanced_daily(items: list[dict[str, Any]], target_records: int = 10, max_records: int = 12) -> list[dict[str, Any]]:
    buckets = {
        "classic_highly_cited_english": lambda item: item.get("language") == "en" and (item.get("citation_count") or 0) >= 50,
        "transferable_management_communication": lambda item: item.get("matched_category") == "transferable_management_communication",
        "management_transfer": lambda item: item.get("matched_category") == "management_transfer" or "management_transfer" in (item.get("matched_topics") or []),
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
        if len(selected) >= max_records:
            break
        key = item_key(item)
        if key not in seen:
            selected.append(item)
            seen.add(key)
    return selected[:max_records if len(selected) >= target_records else len(selected)]


def balanced_weekly(items: list[dict[str, Any]], max_records: int = 4) -> list[dict[str, Any]]:
    zh = [item for item in items if item.get("language") == "zh"]
    en = [item for item in items if item.get("language") != "zh"]
    selected = zh[:2] + en[:2]
    seen = {item_key(item) for item in selected}
    for item in items:
        if len(selected) >= max_records:
            break
        key = item_key(item)
        if key not in seen:
            selected.append(item)
            seen.add(key)
    return selected[:max_records]


def target_count(mode: str) -> int:
    return 4 if mode == "weekly" else 8


def build_diagnostics(
    discovery_stats: dict[str, int],
    candidate_total: int,
    final_count: int,
    duplicate_count: int,
    block_counts: dict[str, int],
    filtered_reasons: list[dict[str, str]],
    topic_diagnostics: dict[str, Any],
    selected_diagnostics_data: dict[str, Any],
    time_window: dict[str, Any],
    mode: str,
    dry_run: bool,
    send_empty_digest: bool,
    per_query: int,
    target_records: int,
    max_records: int,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = dict(discovery_stats)
    diagnostics["mode"] = mode
    diagnostics["dry_run"] = dry_run
    diagnostics["send_empty_digest"] = send_empty_digest
    diagnostics.update(time_window)
    diagnostics["per_query"] = per_query
    diagnostics["candidate_pool_size"] = max(candidate_total, 150 if mode == "daily" else candidate_total)
    diagnostics["candidate_total_before_filter"] = candidate_total
    diagnostics["final_email_record_count"] = final_count
    diagnostics["duplicate_or_already_pushed_count"] = duplicate_count
    diagnostics["after_hard_filter_count"] = candidate_total - block_counts.get("blocked_by_document_type_count", 0) - block_counts.get("blocked_by_exclusion_rules_count", 0) - block_counts.get("blocked_by_future_date_count", 0)
    diagnostics["after_topic_filter_count"] = candidate_total - block_counts.get("blocked_by_uncategorized_count", 0)
    diagnostics["after_score_filter_count"] = max(0, candidate_total - block_counts.get("blocked_by_score_threshold_count", 0))
    diagnostics["after_duplicate_filter_count"] = final_count
    diagnostics["target_records"] = target_records
    diagnostics["max_records"] = max_records
    diagnostics.update(block_counts)
    diagnostics["top_filtered_records"] = filtered_reasons
    diagnostics.update(topic_diagnostics)
    diagnostics.update(selected_diagnostics_data)
    return diagnostics


def log_diagnostics(diagnostics: dict[str, Any]) -> None:
    for key in [
        "mode",
        "dry_run",
        "time_window_strategy",
        "since_date",
        "until_date",
        "fallback_backfill_days",
        "last_successful_run_at",
        "current_run_started_at",
        "per_query",
        "candidate_pool_size",
        "send_empty_digest",
        "loaded_journal_zh_count",
        "loaded_journal_en_count",
        "journal_whitelist_discovery_count",
        "fetched_from_openalex_journal_count",
        "fetched_from_semantic_scholar_count",
        "candidate_total_before_filter",
        "after_hard_filter_count",
        "after_topic_filter_count",
        "after_score_filter_count",
        "after_duplicate_filter_count",
        "final_email_record_count",
        "target_records",
        "max_records",
        "matched_topics_count",
        "matched_topics_distribution",
        "selected_topic_distribution",
        "selected_journal_distribution",
        "duplicate_or_already_pushed_count",
        "blocked_by_score_threshold_count",
        "blocked_by_missing_journal_count",
        "blocked_by_uncategorized_count",
        "blocked_by_crossref_only_count",
        "blocked_by_document_type_count",
        "blocked_by_exclusion_rules_count",
        "blocked_by_future_date_count",
    ]:
        LOGGER.info("%s=%s", key, diagnostics.get(key, 0))
    if diagnostics.get("mode") == "daily" and int(diagnostics.get("final_email_record_count", 0) or 0) < 5:
        LOGGER.info("daily selected fewer than 5 records because:")
        LOGGER.info("candidate pool too small: %s", diagnostics.get("candidate_pool_size", 0))
        LOGGER.info("topic unmatched: %s", diagnostics.get("blocked_by_uncategorized_count", 0))
        LOGGER.info("score below threshold: %s", diagnostics.get("blocked_by_score_threshold_count", 0))
        LOGGER.info("duplicate/already pushed: %s", diagnostics.get("duplicate_or_already_pushed_count", 0))
        LOGGER.info("missing journal/source: %s", diagnostics.get("blocked_by_missing_journal_count", 0))
        LOGGER.info("hard exclusion rules: %s", diagnostics.get("blocked_by_exclusion_rules_count", 0))
        LOGGER.info("future date/year excluded: %s", diagnostics.get("blocked_by_future_date_count", 0))
    for item in diagnostics.get("top_uncategorized_records", [])[:5]:
        LOGGER.info("uncategorized_record title=%r journal=%r source_api=%r", item.get("title"), item.get("journal"), item.get("source_api"))
    for item in diagnostics.get("top_filtered_records", [])[:5]:
        LOGGER.info(
            "filtered_record %s | %s | %s | %s | %s | %s",
            item.get("title"),
            item.get("journal"),
            item.get("source_api"),
            item.get("matched_topics"),
            item.get("score"),
            item.get("block_reason"),
        )


def evaluate_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    topic_groups = load_topic_groups()
    journal_names = load_journal_names()
    exclusions = load_exclusion_rules()
    return [score_item(dict(item), topic_groups, journal_names, exclusions) for item in items]


def block_counts_from_evaluated(evaluated: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "blocked_by_score_threshold_count": 0,
        "blocked_by_missing_journal_count": 0,
        "blocked_by_uncategorized_count": 0,
        "blocked_by_crossref_only_count": 0,
        "blocked_by_document_type_count": 0,
        "blocked_by_exclusion_rules_count": 0,
        "blocked_by_future_date_count": 0,
    }
    for item in evaluated:
        reason = filter_reason(item)
        if "score threshold" in reason or item.get("priority") == "C":
            counts["blocked_by_score_threshold_count"] += 1
        if "missing journal" in reason:
            counts["blocked_by_missing_journal_count"] += 1
        if "uncategorized" in reason:
            counts["blocked_by_uncategorized_count"] += 1
        if "crossref-only" in reason:
            counts["blocked_by_crossref_only_count"] += 1
        if "work_type" in reason:
            counts["blocked_by_document_type_count"] += 1
        if "exclusion" in reason:
            counts["blocked_by_exclusion_rules_count"] += 1
        if "future" in reason:
            counts["blocked_by_future_date_count"] += 1
    return counts


def selected_diagnostics(items: list[dict[str, Any]]) -> dict[str, Any]:
    topic_distribution: dict[str, int] = {}
    journal_distribution: dict[str, int] = {}
    for item in items:
        topics = item.get("matched_topics") or [item.get("matched_category") or item.get("category") or "uncategorized"]
        for topic in topics:
            topic_distribution[str(topic)] = topic_distribution.get(str(topic), 0) + 1
        journal = str(item.get("venue") or "missing")
        journal_distribution[journal] = journal_distribution.get(journal, 0) + 1
    return {
        "selected_topic_distribution": topic_distribution,
        "selected_journal_distribution": journal_distribution,
    }


def topic_diagnostics_from_evaluated(evaluated: list[dict[str, Any]]) -> dict[str, Any]:
    distribution: dict[str, int] = {}
    topic_matched_count = 0
    uncategorized: list[dict[str, str]] = []
    for item in evaluated:
        topics = item.get("matched_topics") or []
        if topics:
            topic_matched_count += 1
            for topic in topics:
                distribution[str(topic)] = distribution.get(str(topic), 0) + 1
        else:
            uncategorized.append(
                {
                    "title": str(item.get("title", "missing")),
                    "journal": str(item.get("venue", "missing")),
                    "source_api": str(item.get("source_api") or item.get("source") or "missing"),
                }
            )
    return {
        "matched_topics_count": topic_matched_count,
        "matched_topics_distribution": distribution,
        "top_uncategorized_records": uncategorized[:8],
    }


def top_filtered_records(evaluated: list[dict[str, Any]]) -> list[dict[str, str]]:
    filtered: list[dict[str, str]] = []
    for item in evaluated:
        if item.get("eligible_for_email"):
            continue
        filtered.append(
            {
                "title": str(item.get("title", "missing")),
                "source_api": str(item.get("source_api") or item.get("source") or "missing"),
                "journal": str(item.get("venue") or "missing"),
                "matched_topics": ",".join(str(topic) for topic in item.get("matched_topics", [])) or "missing",
                "score": str(item.get("score", "missing")),
                "priority": str(item.get("priority", "missing")),
                "block_reason": filter_reason(item),
            }
        )
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
    if not item.get("matched_topics"):
        return "uncategorized"
    if is_future_item(item):
        return "future publication year/date"
    if item.get("future_date"):
        return "future publication year/date"
    work_type = str(item.get("work_type", "")).casefold()
    if work_type in {"book", "book-chapter", "chapter", "component", "monograph", "proceedings", "proceedings-article"}:
        return f"blocked work_type={work_type}"
    if int(item.get("quality_penalties", 0) or 0) >= 100:
        return "blocked by exclusion rules or hard quality rule"
    if missing_value(item.get("abstract")):
        return "missing abstract"
    if item.get("priority") == "C" or int(item.get("score", 0) or 0) < (70 if item.get("alert_mode") == "weekly" else 65):
        return "blocked by score threshold"
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
        f"- time_window_strategy: {diagnostics.get('time_window_strategy', 'missing')}",
        f"- since_date: {diagnostics.get('since_date', 'missing')}",
        f"- until_date: {diagnostics.get('until_date', 'missing')}",
        f"- fallback_backfill_days: {diagnostics.get('fallback_backfill_days', 'missing')}",
        f"- current_run_started_at: {diagnostics.get('current_run_started_at', 'missing')}",
        f"- per_query: {diagnostics.get('per_query', 0)}",
        f"- candidate_pool_size: {diagnostics.get('candidate_pool_size', 0)}",
        f"- after_hard_filter_count: {diagnostics.get('after_hard_filter_count', 0)}",
        f"- after_topic_filter_count: {diagnostics.get('after_topic_filter_count', 0)}",
        f"- after_score_filter_count: {diagnostics.get('after_score_filter_count', 0)}",
        f"- after_duplicate_filter_count: {diagnostics.get('after_duplicate_filter_count', 0)}",
        f"- final_email_record_count: {diagnostics.get('final_email_record_count', 0)}",
        f"- target_records: {diagnostics.get('target_records', 0)}",
        f"- max_records: {diagnostics.get('max_records', 0)}",
        f"- matched_topics_count: {diagnostics.get('matched_topics_count', 0)}",
        f"- matched_topics_distribution: {diagnostics.get('matched_topics_distribution', {})}",
        f"- selected_topic_distribution: {diagnostics.get('selected_topic_distribution', {})}",
        f"- selected_journal_distribution: {diagnostics.get('selected_journal_distribution', {})}",
        f"- duplicate_or_already_pushed_count: {diagnostics.get('duplicate_or_already_pushed_count', 0)}",
        f"- blocked_by_score_threshold_count: {diagnostics.get('blocked_by_score_threshold_count', 0)}",
        f"- blocked_by_missing_journal_count: {diagnostics.get('blocked_by_missing_journal_count', 0)}",
        f"- blocked_by_uncategorized_count: {diagnostics.get('blocked_by_uncategorized_count', 0)}",
        f"- blocked_by_crossref_only_count: {diagnostics.get('blocked_by_crossref_only_count', 0)}",
        f"- blocked_by_document_type_count: {diagnostics.get('blocked_by_document_type_count', 0)}",
        f"- blocked_by_exclusion_rules_count: {diagnostics.get('blocked_by_exclusion_rules_count', 0)}",
        f"- blocked_by_future_date_count: {diagnostics.get('blocked_by_future_date_count', 0)}",
        "",
        "### Top Uncategorized Records",
        "",
        "title | journal | source_api",
        "--- | --- | ---",
    ]
    uncategorized = diagnostics.get("top_uncategorized_records", [])
    if uncategorized:
        for item in uncategorized[:5]:
            lines.append(f"{item.get('title', 'missing')} | {item.get('journal', 'missing')} | {item.get('source_api', 'missing')}")
    else:
        lines.append("None | missing | missing")
    lines.extend(
        [
        "",
        "### Top Filtered Records",
        "",
        "title | journal | source_api | matched_topics | score | block_reason",
        "--- | --- | --- | --- | --- | ---",
        ]
    )
    filtered = diagnostics.get("top_filtered_records", [])
    if filtered:
        for item in filtered[:5]:
            lines.append(
                " | ".join(
                    [
                        str(item.get("title", "missing")),
                        str(item.get("journal", "missing")),
                        str(item.get("source_api", "missing")),
                        str(item.get("matched_topics", "missing")),
                        str(item.get("score", "missing")),
                        str(item.get("block_reason", "unknown")),
                    ]
                )
            )
    else:
        lines.append("None | missing | missing | missing | missing | missing")
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
