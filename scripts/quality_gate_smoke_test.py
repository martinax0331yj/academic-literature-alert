from __future__ import annotations

import os
from pathlib import Path

from fetch_literature import fetch_serpapi_google_scholar
from fetch_literature import load_journal_whitelist
from journal_config import load_yaml_file
from score_literature import load_exclusion_rules, load_journal_names, load_topic_groups, score_item, score_items


def main() -> None:
    items = [
        {
            "title": "Francis Academic Press foreign journal call for papers",
            "authors": ["Spam Publisher"],
            "year": "2026",
            "venue": "Francis Academic Press",
            "doi": "",
            "url": "",
            "abstract": "Call for papers for foreign journals.",
            "source": "crossref",
            "category": "academic_publishing",
            "language": "en",
            "citation_count": 0,
            "published_date": "2026",
            "work_type": "journal-article",
        },
        {
            "title": "Conflict Resolution and Mediation Skills, Third Edition",
            "authors": ["Book Author"],
            "year": "2026",
            "venue": "Book",
            "doi": "",
            "url": "",
            "abstract": "A chapter from the third edition.",
            "source": "crossref",
            "category": "publishing_management",
            "language": "en",
            "citation_count": 0,
            "published_date": "2026",
            "work_type": "book-chapter",
        },
        {
            "title": "Digital publishing futures in 2027",
            "authors": ["Future Author"],
            "year": "2027",
            "venue": "Learned Publishing",
            "doi": "10.0000/future",
            "url": "https://example.test/future",
            "abstract": "A future publication record.",
            "source": "openalex",
            "category": "digital_publishing",
            "language": "en",
            "citation_count": 20,
            "published_date": "2027-01-01",
            "work_type": "journal-article",
        },
        {
            "title": "Broad management keyword only",
            "authors": ["Low Relevance"],
            "year": "2026",
            "venue": "Unknown Journal",
            "doi": "",
            "url": "",
            "abstract": "Management keyword without publishing relevance.",
            "source": "openalex",
            "category": "publishing_management",
            "language": "en",
            "citation_count": 0,
            "published_date": "2026",
            "work_type": "journal-article",
        },
        {
            "title": "A crossref only paper about scholarly publishing",
            "authors": ["Crossref Only"],
            "year": "2026",
            "venue": "Unknown Journal",
            "doi": "10.61726/bad",
            "url": "",
            "abstract": "scholarly publishing and peer review",
            "source": "crossref",
            "is_crossref_only": True,
            "category": "academic_publishing",
            "language": "en",
            "citation_count": 99,
            "published_date": "2026",
            "work_type": "journal-article",
        },
        {
            "title": "Google Scholar candidate without journal source",
            "authors": ["Candidate"],
            "year": "2026",
            "venue": "missing",
            "doi": "",
            "url": "https://example.test/scholar",
            "abstract": "missing",
            "search_snippet": "scholarly publishing platform governance",
            "source": "serpapi_google_scholar",
            "source_api": "serpapi_google_scholar",
            "discovery_source": "google_scholar",
            "is_crossref_only": False,
            "category": "academic_publishing",
            "language": "en",
            "citation_count": 40,
            "published_date": "2026",
            "work_type": "journal-article",
        },
        {
            "title": "Google Scholar candidate without confirmed document type",
            "authors": ["Candidate"],
            "year": "2026",
            "venue": "Learned Publishing",
            "doi": "",
            "url": "https://example.test/scholar-type",
            "abstract": "scholarly publishing platform governance peer review open access journal management",
            "search_snippet": "scholarly publishing platform governance",
            "source": "serpapi_google_scholar+openalex",
            "source_api": "serpapi_google_scholar",
            "discovery_source": "google_scholar",
            "is_crossref_only": False,
            "category": "academic_publishing",
            "language": "en",
            "citation_count": 40,
            "published_date": "2026",
            "work_type": "",
        },
        {
            "title": "数字出版平台治理与知识服务研究",
            "authors": ["中文作者"],
            "year": "2026",
            "venue": "Unknown Journal",
            "doi": "",
            "url": "https://example.test/zh-weekly",
            "abstract": "数字出版 平台治理 知识服务 出版企业管理",
            "source": "openalex",
            "category": "digital_publishing",
            "language": "zh",
            "citation_count": 50,
            "published_date": "2026",
            "work_type": "journal-article",
            "alert_mode": "weekly",
        },
        {
            "title": "Peer review governance in scholarly publishing platforms",
            "authors": ["Good Author"],
            "year": "2026",
            "venue": "Learned Publishing",
            "doi": "10.0000/good",
            "url": "https://example.test/good",
            "abstract": "This article studies peer review governance, scholarly publishing platforms, open access, and journal management.",
            "source": "openalex",
            "category": "academic_publishing",
            "language": "en",
            "citation_count": 25,
            "published_date": "2026-01-01",
            "work_type": "journal-article",
        },
        {
            "title": "Open access and peer review governance in scholarly publishing platforms",
            "authors": ["Zero Citation"],
            "year": "2026",
            "venue": "Learned Publishing",
            "doi": "10.0000/zero-citation",
            "url": "https://example.test/zero-citation",
            "abstract": "This article studies scholarly publishing, peer review, open access, journal management, platform governance, and research integrity.",
            "source": "openalex",
            "discovery_source": "journal_whitelist",
            "whitelist_matched": True,
            "category": "academic_publishing",
            "language": "en",
            "citation_count": 0,
            "published_date": "2026-01-01",
            "work_type": "journal-article",
        },
        {
            "title": "组织能力、品牌资产与平台治理机制研究",
            "authors": ["管理作者"],
            "year": "2026",
            "venue": "管理世界",
            "doi": "10.0000/management-transfer-zh",
            "url": "https://example.test/management-transfer-zh",
            "abstract": "本文基于资源基础观和动态能力理论，探讨组织能力、品牌资产与平台治理之间的关系。",
            "source": "openalex",
            "category": "",
            "language": "zh",
            "citation_count": 0,
            "published_date": "2026-01-01",
            "work_type": "journal-article",
        },
        {
            "title": "Platform governance and brand equity in digital transformation",
            "authors": ["Management Author"],
            "year": "2026",
            "venue": "Organization Science",
            "doi": "10.0000/management-transfer-en",
            "url": "https://example.test/management-transfer-en",
            "abstract": "This study examines platform governance, organizational capability and brand equity in digital transformation.",
            "source": "openalex",
            "category": "",
            "language": "en",
            "citation_count": 0,
            "published_date": "2026-01-01",
            "work_type": "journal-article",
        },
        {
            "title": "Open access publishing and peer review reform",
            "authors": ["Publishing Author"],
            "year": "2026",
            "venue": "Learned Publishing",
            "doi": "10.0000/academic-publishing-topic",
            "url": "https://example.test/academic-publishing-topic",
            "abstract": "This paper studies open access publishing, peer review and scholarly communication.",
            "source": "openalex",
            "category": "",
            "language": "en",
            "citation_count": 0,
            "published_date": "2026-01-01",
            "work_type": "journal-article",
        },
        {
            "title": "Future dated scholarly publishing article",
            "authors": ["Future Author"],
            "year": "2027",
            "venue": "Learned Publishing",
            "doi": "10.0000/future-date",
            "url": "https://example.test/future-date",
            "abstract": "This article studies scholarly publishing and peer review.",
            "source": "openalex",
            "category": "academic_publishing",
            "language": "en",
            "citation_count": 50,
            "published_date": "2027-01-01",
            "work_type": "journal-article",
        },
    ]
    scored = score_items(items)
    topic_groups = load_topic_groups()
    journal_names = load_journal_names()
    exclusions = load_exclusion_rules()
    evaluated = {item["title"]: score_item(dict(item), topic_groups, journal_names, exclusions) for item in items}
    titles = {item["title"] for item in scored}
    assert "Francis Academic Press foreign journal call for papers" not in titles
    assert "Conflict Resolution and Mediation Skills, Third Edition" not in titles
    assert "Digital publishing futures in 2027" not in titles
    assert "Broad management keyword only" not in titles
    assert "A crossref only paper about scholarly publishing" not in titles
    assert "Google Scholar candidate without journal source" not in titles
    assert "Google Scholar candidate without confirmed document type" not in titles
    assert "数字出版平台治理与知识服务研究" not in titles
    assert "Peer review governance in scholarly publishing platforms" in titles
    assert "Open access and peer review governance in scholarly publishing platforms" in titles
    assert "Future dated scholarly publishing article" not in titles
    assert "management_transfer" in evaluated["组织能力、品牌资产与平台治理机制研究"]["matched_topics"]
    assert evaluated["组织能力、品牌资产与平台治理机制研究"]["matched_category"] != "uncategorized"
    assert "management_transfer" in evaluated["Platform governance and brand equity in digital transformation"]["matched_topics"]
    assert evaluated["Platform governance and brand equity in digital transformation"]["matched_category"] != "uncategorized"
    academic_topics = evaluated["Open access publishing and peer review reform"]["matched_topics"]
    assert "academic_publishing" in academic_topics or "scholarly_communication" in academic_topics
    assert evaluated["Open access publishing and peer review reform"]["matched_category"] != "uncategorized"
    assert not evaluated["Future dated scholarly publishing article"]["eligible_for_email"]
    schedules = load_yaml_file(Path("config/schedules.yml"))
    assert schedules["daily"]["start_from"] == "last_successful_run"
    assert schedules["daily"]["fallback_backfill_days"] == 90
    assert schedules["daily"]["target_records"] == 10
    assert schedules["daily"]["max_records"] == 12
    assert schedules["weekly"]["lookback_days"] == 180
    assert all(item["priority"] in {"A", "B"} for item in scored)
    journals = load_journal_whitelist()
    assert len([journal for journal in journals if journal.get("language") == "zh"]) >= 40
    assert len([journal for journal in journals if journal.get("language") == "en"]) >= 54
    old_key = os.environ.pop("SERPAPI_API_KEY", None)
    try:
        assert fetch_serpapi_google_scholar("scholarly publishing", 1) == []
    finally:
        if old_key is not None:
            os.environ["SERPAPI_API_KEY"] = old_key
    print("quality gate smoke test passed")


if __name__ == "__main__":
    main()
