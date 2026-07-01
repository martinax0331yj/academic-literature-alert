from __future__ import annotations

import csv
import os
import json
import logging
import time
from dataclasses import dataclass, field
import hashlib
import re
from datetime import date
from pathlib import Path
from typing import Any

from journal_config import load_yaml_file

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
LAST_DISCOVERY_STATS = {
    "loaded_journal_zh_count": 0,
    "loaded_journal_en_count": 0,
    "journal_whitelist_discovery_count": 0,
    "fetched_from_openalex_journal_count": 0,
    "fetched_from_semantic_scholar_count": 0,
}

DEFAULT_TOPIC_QUERIES = {
    "academic_publishing": ["scholarly publishing", "open access", "peer review"],
    "publishing_management": ["publishing management", "brand", "copyright"],
    "digital_publishing": ["digital publishing", "digital reading", "digital content"],
    "game_and_interactive_publishing": ["game publishing", "interactive narrative", "transmedia"],
    "transferable_management_communication": ["platform governance", "user engagement", "media management"],
    "technology_frontier": ["generative AI", "large language model", "AI ethics"],
}

DEFAULT_SOURCE_POLICY = {
    "source_policy": {
        "serpapi_google_scholar": {
            "enabled": True,
            "api_key_env": "SERPAPI_API_KEY",
            "engine": "google_scholar",
            "max_results_per_query": 10,
        },
        "crossref": {"reject_crossref_only_items": True},
    }
}

WEEKLY_SCHOLAR_QUERIES = [
    '"scholarly publishing" OR "academic publishing" OR "journal management"',
    '"digital publishing" OR "smart publishing" OR "publishing platform"',
    '"game publishing" OR "interactive narrative" OR "digital games industry"',
    '"generative AI" AND publishing',
    '"peer review" AND "research integrity"',
]


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
    config = load_yaml_file(path, yaml)
    if config:
        return config
    if yaml is None:
        LOGGER.warning("PyYAML is not installed; using built-in default topic queries.")
        return {}
    return {}


def topic_queries(topics_path: Path = ROOT / "config" / "topics.yml") -> dict[str, list[str]]:
    config = load_yaml(topics_path)
    groups = config.get("groups", {})
    return {name: values.get("keywords", []) for name, values in groups.items()} or DEFAULT_TOPIC_QUERIES


def source_policy(path: Path = ROOT / "config" / "source_policy.yml") -> dict[str, Any]:
    config = load_yaml(path)
    return config or DEFAULT_SOURCE_POLICY


def get_discovery_stats() -> dict[str, int]:
    return dict(LAST_DISCOVERY_STATS)


def reset_discovery_stats() -> None:
    for key in LAST_DISCOVERY_STATS:
        LAST_DISCOVERY_STATS[key] = 0


def load_journal_whitelist() -> list[dict[str, Any]]:
    journals: list[dict[str, Any]] = []
    for path, language in [
        (ROOT / "config" / "journals_zh.yml", "zh"),
        (ROOT / "config" / "journals_en.yml", "en"),
    ]:
        config = load_yaml(path)
        journals.extend(normalize_journal_entries(config, language))
    LAST_DISCOVERY_STATS["loaded_journal_zh_count"] = sum(1 for journal in journals if journal.get("language") == "zh")
    LAST_DISCOVERY_STATS["loaded_journal_en_count"] = sum(1 for journal in journals if journal.get("language") == "en")
    return journals


def normalize_journal_entries(config: dict[str, Any], default_language: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if isinstance(config.get("journals"), list):
        for raw in config["journals"]:
            name = str(raw.get("name") or raw.get("journal") or "").strip()
            if name:
                entries.append(normalize_journal_entry(raw, name, default_language))
    for journals in (config.get("fields") or {}).values():
        for raw in journals:
            name = str(raw.get("name") or raw.get("journal") or "").strip()
            if name:
                entries.append(normalize_journal_entry(raw, name, default_language))
    return dedupe_journals(entries)


def normalize_journal_entry(raw: dict[str, Any], name: str, default_language: str) -> dict[str, Any]:
    aliases = raw.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    discovery = raw.get("discovery") or {}
    return {
        "name": name,
        "language": raw.get("language") or default_language,
        "enabled": bool(raw.get("enabled", True)),
        "aliases": [str(alias).strip() for alias in aliases if str(alias).strip()],
        "issn": str(raw.get("issn", "") or ""),
        "eissn": str(raw.get("eissn", "") or ""),
        "openalex_source_id": str(raw.get("openalex_source_id", "") or raw.get("source_id", "") or ""),
        "source_id": str(raw.get("source_id", "") or raw.get("openalex_source_id", "") or ""),
        "quality_tags": list(raw.get("quality_tags") or []),
        "subject_tags": list(raw.get("subject_tags") or []),
        "discovery": {
            "use_openalex": bool(discovery.get("use_openalex", True)),
            "use_semantic_scholar": bool(discovery.get("use_semantic_scholar", default_language == "en")),
            "use_cnki_import": bool(discovery.get("use_cnki_import", default_language == "zh")),
            "use_google_scholar_import": bool(discovery.get("use_google_scholar_import", default_language == "en")),
            "use_official_site": bool(discovery.get("use_official_site", False)),
        },
        "metadata_status": raw.get("metadata_status", "unresolved"),
        "metadata_note": raw.get("metadata_note") or raw.get("quality_note") or "",
    }


def dedupe_journals(journals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for journal in journals:
        key = str(journal.get("name", "")).casefold()
        if not key:
            continue
        if key not in merged:
            merged[key] = journal
            order.append(key)
            continue
        existing = merged[key]
        existing["aliases"] = sorted(set(existing.get("aliases", [])) | set(journal.get("aliases", [])))
        existing["quality_tags"] = sorted(set(existing.get("quality_tags", [])) | set(journal.get("quality_tags", [])))
        existing["subject_tags"] = sorted(set(existing.get("subject_tags", [])) | set(journal.get("subject_tags", [])))
        for field in ["issn", "eissn", "openalex_source_id", "source_id", "metadata_status", "metadata_note"]:
            if not existing.get(field) and journal.get(field):
                existing[field] = journal[field]
    return [merged[key] for key in order]


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


def fetch_crossref_by_doi(doi: str, timeout: int = 20) -> dict[str, Any] | None:
    if requests is None:
        raise RuntimeError("requests is not installed")
    normalized = normalize_doi(doi)
    if not normalized:
        return None
    url = f"https://api.crossref.org/works/{normalized}"
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "academic-literature-alert/0.1"})
    response.raise_for_status()
    work = response.json().get("message", {})
    title = first_value(work.get("title"))
    if not title:
        return None
    published = work.get("published-print") or work.get("published-online") or work.get("created") or {}
    year = first_date_part(published)
    authors = [
        " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part).strip()
        for author in work.get("author", [])
    ]
    return LiteratureItem(
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
    ).to_dict()


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


def fetch_openalex_by_doi(doi: str, timeout: int = 20) -> dict[str, Any] | None:
    if requests is None:
        raise RuntimeError("requests is not installed")
    normalized = normalize_doi(doi)
    if not normalized:
        return None
    url = f"https://api.openalex.org/works/https://doi.org/{normalized}"
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "academic-literature-alert/0.1"})
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return openalex_work_to_item(response.json()).to_dict()


def fetch_openalex_source_by_issn(issn: str, timeout: int = 20) -> dict[str, Any] | None:
    if requests is None:
        raise RuntimeError("requests is not installed")
    normalized = normalize_issn(issn)
    if not normalized:
        return None
    url = f"https://api.openalex.org/sources/issn:{normalized}"
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "academic-literature-alert/0.1"})
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def search_openalex_sources(query: str, rows: int = 3, timeout: int = 20) -> list[dict[str, Any]]:
    if requests is None:
        raise RuntimeError("requests is not installed")
    url = "https://api.openalex.org/sources"
    params = {"search": query, "per-page": rows}
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "academic-literature-alert/0.1"})
    response.raise_for_status()
    return response.json().get("results", [])


def openalex_source_id_from_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("https://openalex.org/"):
        return text.rsplit("/", 1)[-1]
    return text


def resolve_openalex_source_for_journal(journal: dict[str, Any]) -> tuple[str, str]:
    explicit = openalex_source_id_from_url(journal.get("openalex_source_id") or journal.get("source_id") or "")
    if explicit:
        return explicit, "openalex_source_id"
    for identifier in [journal.get("issn"), journal.get("eissn")]:
        if not identifier:
            continue
        source = fetch_openalex_source_by_issn(str(identifier))
        if source and source.get("id"):
            return openalex_source_id_from_url(source["id"]), "issn"
    candidates = [journal.get("name", "")] + list(journal.get("aliases", []))
    for query in [candidate for candidate in candidates if candidate]:
        sources = search_openalex_sources(str(query), rows=3)
        exact = [
            source for source in sources
            if str(source.get("display_name", "")).casefold() == str(query).casefold()
        ]
        if len(exact) == 1 and exact[0].get("id"):
            return openalex_source_id_from_url(exact[0]["id"]), "name"
    return "", "unresolved"


def fetch_openalex_works_by_source(source_id: str, since_date: str, rows: int = 5, timeout: int = 20) -> list[dict[str, Any]]:
    if requests is None:
        raise RuntimeError("requests is not installed")
    openalex_id = openalex_source_id_from_url(source_id)
    if not openalex_id:
        return []
    url = "https://api.openalex.org/works"
    params = {
        "filter": f"primary_location.source.id:https://openalex.org/{openalex_id},from_publication_date:{since_date}",
        "sort": "publication_date:desc",
        "per-page": rows,
    }
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "academic-literature-alert/0.1"})
    response.raise_for_status()
    return [openalex_work_to_item(work).to_dict() for work in response.json().get("results", []) if work.get("title")]


def fetch_openalex_by_journals(journals: list[dict[str, Any]], since_date: str, max_per_journal: int = 5) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    enabled = [
        journal for journal in journals
        if journal.get("enabled", True) and (journal.get("discovery") or {}).get("use_openalex", True)
    ]
    LAST_DISCOVERY_STATS["journal_whitelist_discovery_count"] = len(enabled)
    if requests is None:
        LOGGER.warning("fetch_openalex_by_journals skipped: requests is not installed")
        return []
    for journal in enabled:
        try:
            source_id, resolution_method = resolve_openalex_source_for_journal(journal)
            if not source_id:
                continue
            fetched = fetch_openalex_works_by_source(source_id, since_date, rows=max_per_journal)
            for item in fetched:
                item["discovery_source"] = "journal_whitelist"
                item["whitelist_matched"] = True
                item["journal_whitelist_name"] = journal.get("name", "")
                item["journal_source_resolution"] = resolution_method
                item["category"] = category_from_journal(journal)
                item["language"] = item.get("language") or journal.get("language") or "en"
            items.extend(fetched)
            time.sleep(0.2)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("fetch_openalex_by_journals failed for %r: %s", journal.get("name"), exc)
    LAST_DISCOVERY_STATS["fetched_from_openalex_journal_count"] = len(items)
    return items


def category_from_journal(journal: dict[str, Any]) -> str:
    tags = set(journal.get("subject_tags") or [])
    if {"academic_publishing", "scholarly_publishing", "journal_management", "scholarly_communication"} & tags:
        return "academic_publishing"
    if {"digital_publishing", "digital_transformation", "information_systems"} & tags:
        return "digital_publishing"
    if {"game_publishing", "digital_games", "interactive_narrative"} & tags:
        return "game_and_interactive_publishing"
    if {"management", "organization_studies", "strategy", "brand_management", "platform_governance"} & tags:
        return "publishing_management"
    return "uncategorized"


def openalex_work_to_item(work: dict[str, Any]) -> LiteratureItem:
    authors = [
        authorship.get("author", {}).get("display_name", "")
        for authorship in work.get("authorships", [])
        if authorship.get("author", {}).get("display_name")
    ]
    venue = (work.get("primary_location") or {}).get("source") or {}
    return LiteratureItem(
        title=work.get("title") or "",
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


def fetch_semantic_scholar_by_doi(doi: str, timeout: int = 20) -> dict[str, Any] | None:
    if requests is None:
        raise RuntimeError("requests is not installed")
    normalized = normalize_doi(doi)
    if not normalized:
        return None
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{normalized}"
    params = {"fields": "title,authors,year,venue,url,abstract,citationCount,externalIds,publicationTypes,publicationDate,isOpenAccess"}
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "academic-literature-alert/0.1"})
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return semantic_paper_to_item(response.json()).to_dict()


def semantic_paper_to_item(paper: dict[str, Any]) -> LiteratureItem:
    external_ids = paper.get("externalIds") or {}
    return LiteratureItem(
        title=paper.get("title") or "",
        authors=[author.get("name", "") for author in paper.get("authors", []) if author.get("name")],
        year=str(paper.get("year") or "missing"),
        venue=paper.get("venue") or "missing",
        doi=external_ids.get("DOI", "") or "",
        url=paper.get("url", "") or "",
        abstract=paper.get("abstract") or "missing",
        source="semantic_scholar",
        language="en",
        citation_count=paper.get("citationCount"),
        published_date=paper.get("publicationDate") or str(paper.get("year") or ""),
        work_type=semantic_work_type(paper.get("publicationTypes")),
        is_oa=paper.get("isOpenAccess"),
    )


def fetch_serpapi_google_scholar(query: str, max_results: int, since_year: int | None = None, timeout: int = 20) -> list[dict[str, Any]]:
    policy = source_policy().get("source_policy", {}).get("serpapi_google_scholar", {})
    api_key_env = policy.get("api_key_env", "SERPAPI_API_KEY")
    api_key = os.getenv(api_key_env)
    if not policy.get("enabled", True):
        LOGGER.info("SerpAPI Google Scholar is disabled by source policy.")
        return []
    if not api_key:
        LOGGER.info("SerpAPI Google Scholar skipped: %s is not configured.", api_key_env)
        return []
    if requests is None:
        raise RuntimeError("requests is not installed")
    params = {
        "engine": policy.get("engine", "google_scholar"),
        "q": query,
        "api_key": api_key,
        "num": max_results,
    }
    if since_year:
        params["as_ylo"] = since_year
    response = requests.get("https://serpapi.com/search.json", params=params, timeout=timeout, headers={"User-Agent": "academic-literature-alert/0.1"})
    response.raise_for_status()
    results = response.json().get("organic_results", [])
    items = [serpapi_result_to_item(result) for result in results if result.get("title")]
    LOGGER.info("SerpAPI Google Scholar fetched count=%s for query=%r", len(items), query)
    return items


def serpapi_result_to_item(result: dict[str, Any]) -> dict[str, Any]:
    publication_info = result.get("publication_info") or {}
    summary = publication_info.get("summary", "") or ""
    authors = []
    for author in publication_info.get("authors", []) or []:
        if author.get("name"):
            authors.append(author["name"])
    item = LiteratureItem(
        title=result.get("title", ""),
        authors=authors,
        year=str(extract_year(summary) or "missing"),
        venue=summary or "missing",
        doi="",
        url=result.get("link", "") or "",
        abstract="missing",
        source="serpapi_google_scholar",
        category="uncategorized",
        language="en",
        citation_count=serpapi_citation_count(result),
        published_date=str(extract_year(summary) or ""),
        work_type="",
    ).to_dict()
    item["source_api"] = "serpapi_google_scholar"
    item["discovery_source"] = "google_scholar"
    item["is_crossref_only"] = False
    item["search_snippet"] = result.get("snippet", "") or ""
    item["preliminary_abstract"] = result.get("snippet", "") or ""
    item["result_id"] = result.get("result_id", "") or ""
    item["cluster_id"] = ((result.get("inline_links") or {}).get("cited_by") or {}).get("cites_id", "") or ""
    return item


def serpapi_citation_count(result: dict[str, Any]) -> int | None:
    cited_by = ((result.get("inline_links") or {}).get("cited_by") or {})
    total = cited_by.get("total")
    return parse_int(total)


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
    reset_discovery_stats()
    queries_by_group = topic_queries()
    journals = load_journal_whitelist()
    selected_groups = ["technology_frontier", "digital_publishing", "academic_publishing"]
    if mode == "weekly":
        selected_groups = ["academic_publishing", "publishing_management", "digital_publishing", "game_and_interactive_publishing"]

    all_items: list[dict[str, Any]] = []
    since_days = 90 if mode == "weekly" else 14
    since_date = date.fromordinal(date.today().toordinal() - since_days).isoformat()
    all_items.extend(fetch_openalex_by_journals(journals, since_date=since_date, max_per_journal=5))
    providers = [fetch_openalex, fetch_semantic_scholar, fetch_crossref]
    for group in selected_groups:
        keywords = queries_by_group.get(group, [])
        query = build_query(group, keywords)
        for scholar_query in scholar_queries_for_group(group, keywords, mode):
            try:
                scholar_items = fetch_serpapi_google_scholar(
                    scholar_query,
                    max_results=serpapi_max_results(),
                    since_year=date.today().year - 5,
                )
                for item in scholar_items:
                    item["category"] = group
                all_items.extend(scholar_items)
                time.sleep(0.2)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("fetch_serpapi_google_scholar failed for query %r: %s", scholar_query, exc)
        for provider in providers:
            try:
                fetched = provider(query, rows=per_query)
                if provider is fetch_semantic_scholar:
                    LAST_DISCOVERY_STATS["fetched_from_semantic_scholar_count"] += len(fetched)
                for item in fetched:
                    item["category"] = group
                    if item.get("source") == "crossref":
                        item["metadata_only"] = True
                all_items.extend(fetched)
                time.sleep(0.2)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("%s failed for query %r: %s", provider.__name__, query, exc)
    return [enrich_metadata(item) for item in merge_metadata(all_items)]


def serpapi_max_results() -> int:
    policy = source_policy().get("source_policy", {}).get("serpapi_google_scholar", {})
    return int(policy.get("max_results_per_query", 10) or 10)


def scholar_queries_for_group(group: str, keywords: list[str], mode: str) -> list[str]:
    if mode == "weekly":
        mapping = {
            "academic_publishing": [WEEKLY_SCHOLAR_QUERIES[0], WEEKLY_SCHOLAR_QUERIES[4]],
            "publishing_management": [WEEKLY_SCHOLAR_QUERIES[0]],
            "digital_publishing": [WEEKLY_SCHOLAR_QUERIES[1], WEEKLY_SCHOLAR_QUERIES[3]],
            "game_and_interactive_publishing": [WEEKLY_SCHOLAR_QUERIES[2]],
        }
        return mapping.get(group, [])[:2]
    base = build_query(group, keywords)
    return [base][:2]


def enrich_metadata(item: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = [dict(item)]
    doi = normalize_doi(str(item.get("doi", "")))
    title = str(item.get("title", ""))
    try:
        if doi:
            for fetcher in [fetch_openalex_by_doi, fetch_semantic_scholar_by_doi, fetch_crossref_by_doi]:
                enriched = fetcher(doi)
                if enriched:
                    candidates.append(enriched)
        elif title:
            for fetcher in [fetch_openalex, fetch_semantic_scholar]:
                results = fetcher(title, rows=1)
                if results:
                    candidates.append(results[0])
            results = fetch_crossref(title, rows=1)
            if results:
                candidates.append(results[0])
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("metadata enrichment failed for %r: %s", title or doi, exc)
    enriched = merge_metadata(candidates)
    if not enriched:
        return item
    merged = enriched[0]
    if item.get("source_api"):
        merged["source_api"] = item.get("source_api")
    if item.get("discovery_source"):
        merged["discovery_source"] = item.get("discovery_source")
    if item.get("search_snippet"):
        merged["search_snippet"] = item.get("search_snippet")
    if item.get("preliminary_abstract"):
        merged["preliminary_abstract"] = item.get("preliminary_abstract")
    if item.get("result_id"):
        merged["result_id"] = item.get("result_id")
    if item.get("cluster_id"):
        merged["cluster_id"] = item.get("cluster_id")
    merged["is_crossref_only"] = is_crossref_only(merged)
    return merged


def is_crossref_only(item: dict[str, Any]) -> bool:
    source = str(item.get("source", "")).casefold()
    return bool(source) and set(source.split("+")) == {"crossref"}


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
