from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import dataclass, field
import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - exercised in minimal local environments
    requests = None

try:
    import yaml
except ImportError:  # pragma: no cover - exercised in minimal local environments
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)

DEFAULT_TOPIC_QUERIES = {
    "academic_publishing": ["scholarly publishing", "open access", "peer review"],
    "publishing_management": ["publishing management", "brand", "copyright"],
    "digital_publishing": ["digital publishing", "digital reading", "digital content"],
    "game_and_interactive_publishing": ["game publishing", "interactive narrative", "transmedia"],
    "transferable_management_communication": ["platform governance", "user engagement", "media management"],
    "technology_frontier": ["generative AI", "large language model", "AI ethics"],
}


@dataclass
class LiteratureItem:
    title: str
    authors: list[str] = field(default_factory=list)
    year: str = "missing"
    venue: str = "missing"
    doi: str = ""
    url: str = ""
    abstract: str = "missing"
    source: str = "manual"
    category: str = "uncategorized"
    language: str = "unknown"
    citation_count: int | None = None
    published_date: str = ""
    work_type: str = ""
    is_oa: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "doi": self.doi,
            "url": self.url,
            "abstract": self.abstract or "missing",
            "source": self.source,
            "category": self.category,
            "language": self.language,
            "citation_count": self.citation_count,
            "published_date": self.published_date,
            "work_type": self.work_type,
            "is_oa": self.is_oa,
        }


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        LOGGER.warning("PyYAML is not installed; using built-in default topic queries.")
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def topic_queries(topics_path: Path = ROOT / "config" / "topics.yml") -> dict[str, list[str]]:
    config = load_yaml(topics_path)
    groups = config.get("groups", {})
    return {name: values.get("keywords", []) for name, values in groups.items()} or DEFAULT_TOPIC_QUERIES


def fetch_crossref(query: str, rows: int = 5, timeout: int = 20) -> list[dict[str, Any]]:
    if requests is None:
        raise RuntimeError("requests is not installed")
    url = "https://api.crossref.org/works"
    params = {"query": query, "rows": rows, "sort": "published", "order": "desc"}
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "academic-literature-alert/0.1"})
    response.raise_for_status()
    works = response.json().get("message", {}).get("items", [])
    items: list[dict[str, Any]] = []
    for work in works:
        title = first_value(work.get("title"))
        if not title:
            continue
        published = work.get("published-print") or work.get("published-online") or work.get("created") or {}
        year = first_date_part(published)
        authors = [
            " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part).strip()
            for author in work.get("author", [])
        ]
        item = LiteratureItem(
            title=title,
            authors=[name for name in authors if name],
            year=str(year or "missing"),
            venue=first_value(work.get("container-title")) or "missing",
            doi=work.get("DOI", "") or "",
            url=work.get("URL", "") or "",
            abstract=strip_crossref_abstract(work.get("abstract", "")) or "missing",
            source="crossref",
            language="en",
            citation_count=work.get("is-referenced-by-count"),
            published_date=str(year or ""),
            work_type=work.get("type", "") or "",
        )
        items.append(item.to_dict())
    return items


def fetch_openalex(query: str, rows: int = 5, timeout: int = 20) -> list[dict[str, Any]]:
    if requests is None:
        raise RuntimeError("requests is not installed")
    url = "https://api.openalex.org/works"
    params = {"search": query, "per-page": rows, "sort": "publication_date:desc"}
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "academic-literature-alert/0.1"})
    response.raise_for_status()
    works = response.json().get("results", [])
    items: list[dict[str, Any]] = []
    for work in works:
        title = work.get("title") or ""
        if not title:
            continue
        authors = [
            authorship.get("author", {}).get("display_name", "")
            for authorship in work.get("authorships", [])
            if authorship.get("author", {}).get("display_name")
        ]
        venue = (work.get("primary_location") or {}).get("source") or {}
        item = LiteratureItem(
            title=title,
            authors=authors,
            year=str(work.get("publication_year") or "missing"),
            venue=venue.get("display_name", "missing") or "missing",
            doi=(work.get("doi") or "").replace("https://doi.org/", ""),
            url=work.get("id", "") or "",
            abstract=inverted_index_to_text(work.get("abstract_inverted_index")) or "missing",
            source="openalex",
            language=work.get("language") or "en",
            citation_count=work.get("cited_by_count"),
            published_date=work.get("publication_date") or "",
            work_type=work.get("type") or work.get("type_crossref") or "",
            is_oa=(work.get("open_access") or {}).get("is_oa"),
        )
        items.append(item.to_dict())
    return items


def fetch_semantic_scholar(query: str, rows: int = 5, timeout: int = 20) -> list[dict[str, Any]]:
    if requests is None:
        raise RuntimeError("requests is not installed")
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": rows,
        "fields": "title,authors,year,venue,url,abstract,citationCount,externalIds,publicationTypes,publicationDate,isOpenAccess",
    }
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "academic-literature-alert/0.1"})
    response.raise_for_status()
    papers = response.json().get("data", [])
    items: list[dict[str, Any]] = []
    for paper in papers:
        title = paper.get("title") or ""
        if not title:
            continue
        external_ids = paper.get("externalIds") or {}
        item = LiteratureItem(
            title=title,
            authors=[author.get("name", "") for author in paper.get("authors", []) if author.get("name")],
            year=str(paper.get("year") or "missing"),
            venue=paper.get("venue") or "missing",
            doi=external_ids.get("DOI", "") or "",
            url=paper.get("url", "") or "",
            abstract=paper.get("abstract") or "missing",
            source="semantic_scholar",
            language="en",
            citation_count=paper.get("citationCount"),
            published_date=str(paper.get("year") or ""),
            work_type=semantic_work_type(paper.get("publicationTypes")),
            is_oa=paper.get("isOpenAccess"),
        )
        items.append(item.to_dict())
    return items


def read_manual_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        LOGGER.warning("Manual record file does not exist: %s", path)
        return []
    if path.suffix.lower() in {".xlsx", ".xls"}:
        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover - depends on local environment
            raise RuntimeError("Reading XLSX files requires pandas and openpyxl. Run pip install -r requirements.txt.") from exc
        frame = pd.read_excel(path)
        rows = frame.fillna("").to_dict(orient="records")
    else:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))

    items: list[dict[str, Any]] = []
    for row in rows:
        title = str(first_existing(row, ["title", "题名", "篇名", "文献标题"]))
        if not title:
            continue
        authors_raw = str(first_existing(row, ["authors", "作者", "author"]))
        item = LiteratureItem(
            title=title,
            authors=[part.strip() for part in authors_raw.replace("；", ";").split(";") if part.strip()],
            year=str(first_existing(row, ["year", "年份", "发表年份", "publication_year"]) or "missing"),
            venue=str(first_existing(row, ["venue", "journal", "期刊", "来源"]) or "missing"),
            doi=str(first_existing(row, ["doi", "DOI"]) or ""),
            url=str(first_existing(row, ["url", "URL", "链接"]) or ""),
            abstract=str(first_existing(row, ["abstract", "摘要"]) or "missing"),
            source=f"manual:{path.name}",
            language=str(first_existing(row, ["language", "语种"]) or "zh"),
            citation_count=parse_int(first_existing(row, ["citation_count", "被引", "引用量"])),
            published_date=str(first_existing(row, ["published_date", "发表日期"]) or ""),
            work_type=str(first_existing(row, ["work_type", "type", "文献类型"]) or "journal-article"),
        )
        items.append(item.to_dict())
    return items


def fetch_open_sources(mode: str, per_query: int = 3) -> list[dict[str, Any]]:
    queries_by_group = topic_queries()
    selected_groups = ["technology_frontier", "digital_publishing", "academic_publishing"]
    if mode == "weekly":
        selected_groups = ["academic_publishing", "publishing_management", "digital_publishing", "game_and_interactive_publishing"]

    all_items: list[dict[str, Any]] = []
    providers = [fetch_openalex, fetch_semantic_scholar, fetch_crossref]
    for group in selected_groups:
        keywords = queries_by_group.get(group, [])
        query = build_query(group, keywords)
        for provider in providers:
            try:
                fetched = provider(query, rows=per_query)
                for item in fetched:
                    item["category"] = group
                    if item.get("source") == "crossref":
                        item["metadata_only"] = True
                all_items.extend(fetched)
                time.sleep(0.2)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("%s failed for query %r: %s", provider.__name__, query, exc)
    return merge_metadata(all_items)


def merge_metadata(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        key = item_key(item)
        if not key:
            continue
        if key not in merged:
            merged[key] = dict(item)
            order.append(key)
            continue
        existing = merged[key]
        existing_sources = {str(part) for part in str(existing.get("source", "")).split("+") if part}
        existing_sources.add(str(item.get("source", "")))
        existing["source"] = "+".join(sorted(existing_sources))
        for field in ["doi", "url", "abstract", "venue", "year", "published_date", "work_type"]:
            if is_missing(existing.get(field)) and not is_missing(item.get(field)):
                existing[field] = item.get(field)
        if not existing.get("authors") and item.get("authors"):
            existing["authors"] = item.get("authors")
        if item.get("citation_count") not in {None, ""}:
            current = existing.get("citation_count")
            try:
                existing["citation_count"] = max(int(current or 0), int(item.get("citation_count") or 0))
            except (TypeError, ValueError):
                existing["citation_count"] = item.get("citation_count")
        existing["metadata_only"] = existing.get("metadata_only") and item.get("metadata_only")
    return [merged[key] for key in order]


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().casefold()
    return not text or text in {"missing", "none", "null", "nan"}


def build_query(group: str, keywords: list[str]) -> str:
    core_queries = {
        "academic_publishing": '"scholarly publishing" OR "journal governance" OR "peer review"',
        "publishing_management": '"publishing management" OR "publishing industry" OR "copyright management"',
        "digital_publishing": '"digital publishing" OR "online literature" OR audiobook',
        "game_and_interactive_publishing": '"game publishing" OR "interactive narrative" OR "transmedia storytelling"',
        "transferable_management_communication": '"brand equity" OR "dynamic capability" OR "platform governance"',
        "technology_frontier": '"generative AI" publishing ethics OR "AI peer review"',
    }
    if group in core_queries:
        return core_queries[group]
    return " ".join(keywords[:3]) if keywords else group


def fallback_items(mode: str) -> list[dict[str, Any]]:
    today = date.today().isoformat()
    seeds = [
        LiteratureItem(
            title="Open access, peer review, and research integrity in scholarly publishing",
            authors=["Metadata Placeholder"],
            year=today[:4],
            venue="open metadata fallback",
            abstract="missing",
            source="fallback_seed",
            category="academic_publishing",
            language="en",
            citation_count=None,
            published_date=today,
            work_type="journal-article",
        ),
        LiteratureItem(
            title="Generative AI and editorial workflows in digital publishing",
            authors=["Metadata Placeholder"],
            year=today[:4],
            venue="open metadata fallback",
            abstract="missing",
            source="fallback_seed",
            category="technology_frontier",
            language="en",
            citation_count=None,
            published_date=today,
            work_type="journal-article",
        ),
        LiteratureItem(
            title="数字内容产品的平台治理与用户参与研究",
            authors=["元数据占位"],
            year=today[:4],
            venue="manual fallback",
            abstract="missing",
            source="fallback_seed",
            category="digital_publishing",
            language="zh",
            citation_count=None,
            published_date=today,
            work_type="journal-article",
        ),
        LiteratureItem(
            title="出版品牌、版权运营与知识服务的组织能力研究",
            authors=["元数据占位"],
            year=today[:4],
            venue="manual fallback",
            abstract="missing",
            source="fallback_seed",
            category="publishing_management",
            language="zh",
            citation_count=None,
            published_date=today,
            work_type="journal-article",
        ),
    ]
    if mode == "daily":
        return [item.to_dict() for item in seeds]
    return [item.to_dict() for item in seeds]


def write_cache(items: list[dict[str, Any]], cache_path: Path = ROOT / "data" / "literature_cache.jsonl") -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    seen = existing_cache_keys(cache_path)
    with cache_path.open("a", encoding="utf-8") as handle:
        for item in items:
            key = item_key(item)
            if key in seen:
                continue
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            seen.add(key)


def existing_cache_keys(cache_path: Path) -> set[str]:
    if not cache_path.exists():
        return set()
    keys: set[str] = set()
    with cache_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                keys.add(item_key(json.loads(line)))
            except json.JSONDecodeError:
                LOGGER.warning("Skipping malformed cache line in %s", cache_path)
    return keys


def item_key(item: dict[str, Any]) -> str:
    doi = normalize_doi(str(item.get("doi", "")))
    if doi:
        return doi
    return title_hash(str(item.get("title", "")))


def normalize_doi(doi: str) -> str:
    return doi.strip().lower().replace("https://doi.org/", "").replace("http://doi.org/", "")


def normalize_title(title: str) -> str:
    return re.sub(r"\W+", "", title.casefold().strip())


def title_hash(title: str) -> str:
    return hashlib.sha256(normalize_title(title).encode("utf-8")).hexdigest()[:16]


def first_value(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    return str(value or "")


def first_date_part(value: dict[str, Any]) -> int | None:
    parts = value.get("date-parts") or []
    if parts and parts[0]:
        return parts[0][0]
    return None


def strip_crossref_abstract(raw: str) -> str:
    return raw.replace("<jats:p>", "").replace("</jats:p>", "").strip()


def inverted_index_to_text(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        words.extend((position, word) for position in positions)
    return " ".join(word for _, word in sorted(words))


def first_existing(row: dict[str, Any], names: list[str]) -> Any:
    lower_map = {str(key).lower(): key for key in row.keys()}
    for name in names:
        key = lower_map.get(name.lower())
        if key is not None and str(row[key]).strip():
            return row[key]
    return ""


def parse_int(value: Any) -> int | None:
    try:
        if value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def semantic_work_type(publication_types: Any) -> str:
    if not publication_types:
        return "journal-article"
    if isinstance(publication_types, list):
        lowered = {str(item).casefold() for item in publication_types}
        if "review" in lowered:
            return "review"
        if "journalarticle" in lowered or "journal article" in lowered:
            return "journal-article"
        if "book" in lowered:
            return "book"
        if "bookchapter" in lowered or "book chapter" in lowered:
            return "book-chapter"
        return str(publication_types[0])
    return str(publication_types)


def write_items_csv(items: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["title", "authors", "year", "venue", "doi", "url", "abstract", "source", "category", "language", "citation_count", "published_date"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: item.get(field, "") for field in fields} for item in items)
