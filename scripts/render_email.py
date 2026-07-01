from __future__ import annotations

from datetime import date
from html import escape
from typing import Any


def render_markdown(items: list[dict[str, Any]], mode: str) -> str:
    run_date = date.today().isoformat()
    sources = sorted({str(item.get("source", "missing")) for item in items})
    lines = [
        f"# Literature Alert - {mode} - {run_date}",
        "",
        "## Summary",
        "",
        f"- Items selected: {len(items)}",
        f"- Data sources: {', '.join(sources) if sources else 'missing'}",
        "- Note: metadata-only alert. No full-text PDF is downloaded or attached.",
        "",
    ]
    for index, item in enumerate(items, 1):
        lines.extend(
            [
                f"## {index}. {item.get('title', 'missing')}",
                "",
                f"- Priority: {item.get('priority', 'missing')} (score: {item.get('score', 'missing')})",
                f"- Category: {item.get('category', 'missing')}",
                f"- Authors: {format_authors(item.get('authors'))}",
                f"- Year/date: {item.get('published_date') or item.get('year') or 'missing'}",
                f"- Venue: {item.get('venue', 'missing')}",
                f"- DOI/URL: {item.get('doi') or item.get('url') or 'missing'}",
                f"- Source: {item.get('source', 'missing')}",
                f"- Abstract: {item.get('abstract') or 'missing'}",
                f"- Recommendation: {item.get('recommendation_reason', 'missing')}",
                f"- Research relation: {item.get('research_relation', 'missing')}",
                "",
            ]
        )
    lines.extend(
        [
            "## Compliance Note",
            "",
            "This email contains metadata and short summaries only. Missing metadata is marked as missing and not fabricated.",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(items: list[dict[str, Any]], mode: str) -> str:
    markdown = render_markdown(items, mode)
    body = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            body.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("- "):
            body.append(f"<li>{escape(line[2:])}</li>")
        elif line.strip():
            body.append(f"<p>{escape(line)}</p>")
    return "<html><body>" + "\n".join(body) + "</body></html>"


def format_authors(authors: Any) -> str:
    if isinstance(authors, list) and authors:
        return ", ".join(str(author) for author in authors)
    if isinstance(authors, str) and authors:
        return authors
    return "missing"
