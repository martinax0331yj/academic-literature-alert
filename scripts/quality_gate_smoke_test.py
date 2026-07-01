from __future__ import annotations

from score_literature import score_items


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
    ]
    scored = score_items(items)
    titles = {item["title"] for item in scored}
    assert "Francis Academic Press foreign journal call for papers" not in titles
    assert "Conflict Resolution and Mediation Skills, Third Edition" not in titles
    assert "Digital publishing futures in 2027" not in titles
    assert "Broad management keyword only" not in titles
    assert "Peer review governance in scholarly publishing platforms" in titles
    assert all(item["priority"] in {"A", "B"} for item in scored)
    print("quality gate smoke test passed")


if __name__ == "__main__":
    main()
