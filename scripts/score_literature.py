from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from journal_config import load_yaml_file

try:
    import yaml
except ImportError:  # pragma: no cover - exercised in minimal local environments
    yaml = None

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TOPIC_GROUPS = {
    "academic_publishing": ["scholarly publishing", "open access", "peer review", "学术出版", "开放获取", "同行评议"],
    "publishing_management": ["publishing management", "brand", "copyright", "出版管理", "出版品牌", "版权"],
    "digital_publishing": ["digital publishing", "digital reading", "digital content", "数字出版", "数字阅读", "数字内容"],
    "game_and_interactive_publishing": ["game publishing", "interactive narrative", "transmedia", "游戏出版", "互动叙事", "跨媒介"],
    "transferable_management_communication": ["platform governance", "user engagement", "media management", "平台治理", "用户参与", "媒介管理"],
    "management_transfer": ["organization capability", "organizational capability", "dynamic capability", "resource-based view", "brand equity", "platform governance", "digital transformation", "组织能力", "动态能力", "资源基础观", "品牌资产", "平台治理", "数字化转型"],
    "technology_frontier": ["generative AI", "large language model", "AI ethics", "生成式 AI", "大语言模型", "AI 伦理"],
}

DEFAULT_JOURNALS = {
    "出版发行研究",
    "中国出版",
    "科技与出版",
    "编辑学报",
    "learned publishing",
    "journal of scholarly publishing",
    "scientometrics",
}

ALLOWED_WORK_TYPES = {
    "article",
    "journal-article",
    "journal article",
    "review",
    "review-article",
    "review article",
}

BLOCKED_WORK_TYPES = {
    "book",
    "book-chapter",
    "chapter",
    "component",
    "monograph",
    "proceedings",
    "proceedings-article",
    "posted-content",
    "dataset",
    "report",
    "reference-entry",
}

BLACKLIST_PATTERNS = [
    "francis academic press",
    "call for papers",
    "call for paper",
    "征稿",
    "外文期刊征稿",
    "第三版",
    "3rd edition",
    "third edition",
    "chapter ",
    "book chapter",
    "解决冲突与调解技巧",
    "conflict resolution and mediation",
]

DEFAULT_EXCLUSION_RULES = {
    "blocked_doi_prefixes": ["10.61726"],
    "blocked_publishers": ["Francis Academic Press", "Clausius Scientific Press", "CSP", "弗朗西斯学术出版社", "克劳修斯科学出版社"],
    "blocked_title_keywords_zh": ["征稿", "投稿", "征文", "会议通知", "会议系列", "出版社", "外文学术期刊征稿", "目录", "序言", "前言", "编者按", "出版说明", "广告", "声明", "预刊"],
    "blocked_title_keywords_en": ["call for papers", "call for submissions", "conference series", "proceedings series", "publisher notice", "advertisement", "announcement", "editorial note", "preface", "foreword", "table of contents"],
}


def load_yaml(path: Path) -> dict[str, Any]:
    return load_yaml_file(path, yaml)


def load_topic_groups(path: Path = ROOT / "config" / "topics.yml") -> dict[str, list[str]]:
    config = load_yaml(path)
    groups = {}
    for name, values in config.get("groups", {}).items():
        if values.get("enabled", True):
            groups[name] = values.get("keywords", [])
    return groups or DEFAULT_TOPIC_GROUPS


def load_journal_names() -> set[str]:
    names: set[str] = set()
    zh = load_yaml(ROOT / "config" / "journals_zh.yml").get("journals", [])
    for item in zh:
        names.add(str(item.get("name", "")).casefold())
        for alias in item.get("aliases", []) or []:
            names.add(str(alias).casefold())
    en_config = load_yaml(ROOT / "config" / "journals_en.yml")
    for item in en_config.get("journals", []) or []:
        names.add(str(item.get("name", "") or item.get("journal", "")).casefold())
        for alias in item.get("aliases", []) or []:
            names.add(str(alias).casefold())
    en_fields = en_config.get("fields", {})
    for journals in en_fields.values():
        for item in journals:
            names.add(str(item.get("journal", "")).casefold())
    return {name for name in names if name} or {name.casefold() for name in DEFAULT_JOURNALS}


def score_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    topic_groups = load_topic_groups()
    journal_names = load_journal_names()
    exclusions = load_exclusion_rules()
    scored = [score_item(item, topic_groups, journal_names, exclusions) for item in items]
    return [item for item in scored if item.get("eligible_for_email")]


def score_item(item: dict[str, Any], topic_groups: dict[str, list[str]], journal_names: set[str], exclusions: dict[str, Any] | None = None) -> dict[str, Any]:
    exclusions = exclusions or load_exclusion_rules()
    text = " ".join(
        str(item.get(key, ""))
        for key in ["title", "abstract", "venue", "category", "publisher", "search_snippet"]
    ).casefold()
    matched_topics, category, relevance = match_topics(text, topic_groups)
    whitelisted = is_whitelisted_venue(item, journal_names)
    source_quality = source_quality_points(item, whitelisted)
    recency = recency_points(item)
    citation = citation_points(item.get("citation_count"))
    transferable = transferable_points(text)
    penalties = quality_penalties(item, text, whitelisted, exclusions)
    score = max(0, min(100, relevance + source_quality + recency + citation + transferable - penalties))

    enriched = dict(item)
    enriched["category"] = item.get("category") or category
    enriched["matched_category"] = category
    enriched["matched_topics"] = matched_topics
    enriched["matched_topics_count"] = len(matched_topics)
    enriched["topic_relevance_points"] = relevance
    enriched["source_quality_points"] = source_quality
    enriched["quality_penalties"] = penalties
    enriched["score"] = score
    enriched["priority"] = priority(score)
    enriched["recommendation_reason"] = recommendation_reason(enriched)
    enriched["research_relation"] = research_relation(enriched)
    enriched["eligible_for_email"] = is_eligible_for_email(enriched, text, whitelisted, exclusions)
    return enriched


def load_exclusion_rules(path: Path = ROOT / "config" / "exclusion_rules.yml") -> dict[str, Any]:
    config = load_yaml(path)
    if not config:
        return DEFAULT_EXCLUSION_RULES
    merged = dict(DEFAULT_EXCLUSION_RULES)
    merged.update(config)
    return merged


def match_topics(text: str, topic_groups: dict[str, list[str]]) -> tuple[list[str], str, int]:
    matched: list[tuple[str, int]] = []
    for group, keywords in topic_groups.items():
        hits = sum(1 for keyword in keywords if keyword.casefold() in text)
        if hits > 0:
            matched.append((group, hits))
    if not matched:
        return [], "uncategorized", 0
    matched.sort(key=lambda item: item[1], reverse=True)
    best_group, best_hits = matched[0]
    relevance = min(35, best_hits * 8)
    return [group for group, _ in matched], best_group, relevance


def is_allowed_work_type(item: dict[str, Any]) -> bool:
    raw = str(item.get("work_type", "") or "").strip().casefold()
    if raw in BLOCKED_WORK_TYPES:
        return False
    return raw in ALLOWED_WORK_TYPES


def is_blacklisted(item: dict[str, Any], text: str, exclusions: dict[str, Any]) -> bool:
    doi = str(item.get("doi", "")).casefold()
    for prefix in exclusions.get("blocked_doi_prefixes", []):
        if doi.startswith(str(prefix).casefold()):
            return True
    for publisher in exclusions.get("blocked_publishers", []):
        if str(publisher).casefold() in text:
            return True
    configured_keywords = exclusions.get("blocked_title_keywords_zh", []) + exclusions.get("blocked_title_keywords_en", [])
    return any(str(pattern).casefold() in text for pattern in BLACKLIST_PATTERNS + configured_keywords)


def is_whitelisted_venue(item: dict[str, Any], journal_names: set[str]) -> bool:
    venue = str(item.get("venue", "")).casefold().strip()
    if not venue or venue == "missing":
        return False
    return venue in journal_names


def source_quality_points(item: dict[str, Any], whitelisted: bool) -> int:
    source = str(item.get("source", "")).casefold()
    if whitelisted:
        return 25
    if "openalex" in source or "semantic_scholar" in source:
        return 15
    if source.startswith("manual:"):
        return 20
    if source == "crossref":
        return 4
    if source == "fallback_seed":
        return 0
    return 8


def quality_penalties(item: dict[str, Any], text: str, whitelisted: bool, exclusions: dict[str, Any]) -> int:
    penalties = 0
    source = str(item.get("source", "")).casefold()
    if item.get("is_crossref_only") or (source == "crossref" and not whitelisted):
        penalties += 15
    if missing(item.get("abstract")):
        penalties += 10
    if missing(item.get("venue")):
        penalties += 10
    if item.get("citation_count") in {None, "", 0, "0"}:
        penalties += 6
    if is_future_item(item):
        penalties += 100
    if not is_allowed_work_type(item):
        penalties += 100
    if is_blacklisted(item, text, exclusions):
        penalties += 100
    return penalties


def is_eligible_for_email(item: dict[str, Any], text: str, whitelisted: bool, exclusions: dict[str, Any]) -> bool:
    if item.get("priority") not in {"A", "B"}:
        return False
    if int(item.get("score", 0)) < quality_threshold(str(item.get("alert_mode", "daily"))):
        return False
    if not item.get("matched_topics"):
        return False
    if item.get("topic_relevance_points", 0) < 8 and not whitelisted:
        return False
    if missing(item.get("venue")):
        return False
    if is_future_item(item):
        return False
    if not is_allowed_work_type(item):
        return False
    if is_blacklisted(item, text, exclusions):
        return False
    source = str(item.get("source", "")).casefold()
    if item.get("is_crossref_only") or (source == "crossref" and not whitelisted):
        return False
    mode = str(item.get("alert_mode", "daily"))
    if mode == "weekly" and not source_allowed_for_weekly(item, source, whitelisted):
        return False
    if source == "fallback_seed":
        return False
    return True


def source_allowed_for_weekly(item: dict[str, Any], source: str, whitelisted: bool) -> bool:
    language = str(item.get("language", "")).casefold()
    discovery_source = str(item.get("discovery_source", "")).casefold()
    source_api = str(item.get("source_api", "")).casefold()
    if language == "zh":
        return whitelisted or source.startswith("manual:")
    allowed_source_signals = [
        "serpapi_google_scholar",
        "openalex",
        "semantic_scholar",
        "publish_or_perish",
        "manual:",
    ]
    if whitelisted:
        return True
    return any(signal in source for signal in allowed_source_signals) or discovery_source == "google_scholar" or source_api == "serpapi_google_scholar"


def quality_threshold(mode: str) -> int:
    return 70 if mode == "weekly" else 65


def missing(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().casefold()
    return not text or text in {"missing", "none", "null", "nan", "未获取"}


def is_future_item(item: dict[str, Any]) -> bool:
    year = extract_year(str(item.get("published_date") or item.get("year") or ""))
    return bool(year and year > date.today().year)


def recency_points(item: dict[str, Any]) -> int:
    year = extract_year(str(item.get("published_date") or item.get("year") or ""))
    if year is None:
        return 5
    age = max(0, date.today().year - year)
    if age <= 1:
        return 15
    if age <= 3:
        return 12
    if age <= 5:
        return 9
    if age <= 10:
        return 6
    return 4


def citation_points(value: Any) -> int:
    if value is None or value == "":
        return 5
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 5
    if count >= 1000:
        return 15
    if count >= 250:
        return 13
    if count >= 50:
        return 10
    if count >= 10:
        return 7
    return 5


def transferable_points(text: str) -> int:
    signals = [
        "platform",
        "governance",
        "capability",
        "brand",
        "user",
        "ai",
        "data",
        "ethics",
        "management",
        "communication",
        "平台",
        "治理",
        "能力",
        "品牌",
        "用户",
        "数据",
        "伦理",
        "管理",
        "传播",
    ]
    hits = sum(1 for signal in signals if signal in text)
    return min(15, hits * 4)


def priority(score: int) -> str:
    if score >= 75:
        return "A"
    if score >= 55:
        return "B"
    return "C"


def recommendation_reason(item: dict[str, Any]) -> str:
    pieces = [
        f"priority {item.get('priority')} with score {item.get('score')}",
        f"matched topic {item.get('matched_category', item.get('category', 'uncategorized'))}",
    ]
    if item.get("citation_count") is None:
        pieces.append("citation count missing")
    else:
        pieces.append(f"citation count {item.get('citation_count')}")
    if item.get("abstract") in {"", "missing", None}:
        pieces.append("abstract missing")
    return "; ".join(pieces)


def research_relation(item: dict[str, Any]) -> str:
    category = item.get("matched_category") or item.get("category") or "uncategorized"
    mapping = {
        "academic_publishing": "Relevant to scholarly publishing, journal governance, peer review, open access, or research integrity.",
        "publishing_management": "Relevant to publishing enterprise management, brand operation, copyright operation, platform governance, or knowledge services.",
        "digital_publishing": "Relevant to digital publishing, integrated publishing, data publishing, reading platforms, or digital content products.",
        "game_and_interactive_publishing": "Relevant to game publishing, interactive narrative, transmedia IP, or virtual communities.",
        "transferable_management_communication": "Provides transferable theories or methods for publishing, media management, communication, or cultural industries.",
        "management_transfer": "Provides transferable management theories or mechanisms for publishing enterprise management, platform governance, brand assets, organizational capability, or digital transformation.",
        "technology_frontier": "Relevant to AI, data governance, recommendation systems, knowledge graphs, or technology-enabled publishing workflows.",
    }
    return mapping.get(category, "Potentially relevant; requires manual expert review.")


def extract_year(value: str) -> int | None:
    match = re.search(r"(19|20)\d{2}", value)
    if not match:
        return None
    return int(match.group(0))
