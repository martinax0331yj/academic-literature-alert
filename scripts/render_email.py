from __future__ import annotations

from datetime import date
from html import escape
from typing import Any


def render_markdown(items: list[dict[str, Any]], mode: str, preview_only: bool = False) -> str:
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
    ]
    if preview_only:
        lines.append("- Preview status: no fresh sendable records; this preview is for inspection only.")
    lines.append("")
    if not items:
        empty_message = empty_digest_message(mode)
        lines.extend(
            [
                "## 暂无符合条件的文献",
                "",
                empty_message,
                "",
            ]
        )
        return "\n".join(lines)
    for index, item in enumerate(items, 1):
        lines.extend(
            [
                f"## {index}. {item.get('title', 'missing')}",
                "",
                f"- 标题: {field(item.get('title'))}",
                f"- 作者: {format_authors(item.get('authors'))}",
                f"- 年份: {field(item.get('year') or item.get('published_date'))}",
                f"- 期刊或来源: {field(item.get('venue'))}",
                f"- DOI: {field(item.get('doi'))}",
                f"- URL: {field(item.get('url'))}",
                f"- 摘要: {field(item.get('abstract'))}",
                f"- 引用量: {field(item.get('citation_count'))}",
                f"- 数据来源: {field(item.get('source'))}",
                f"- 推荐理由: {field(item.get('recommendation_reason'))}",
                f"- 与出版研究的关系: {field(item.get('research_relation'))}",
                f"- 阅读优先级: {field(item.get('priority'))} (score: {field(item.get('score'))})",
                f"- Matched topics: {format_topics(item.get('matched_topics'))}",
                f"- Category: {field(item.get('category'))}",
                "",
            ]
        )
    lines.extend(
        [
            "## Compliance Note",
            "",
            "This email contains metadata and short summaries only. Missing metadata is marked as 未获取 and not fabricated.",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(items: list[dict[str, Any]], mode: str, preview_only: bool = False) -> str:
    markdown = render_markdown(items, mode, preview_only=preview_only)
    return render_html_from_markdown(markdown)


def render_html_from_markdown(markdown: str) -> str:
    body = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            body.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("### "):
            body.append(f"<h3>{escape(line[4:])}</h3>")
        elif line.startswith("- "):
            body.append(f"<li>{escape(line[2:])}</li>")
        elif line.strip():
            body.append(f"<p>{escape(line)}</p>")
    return "<html><body>" + "\n".join(body) + "</body></html>"


def format_authors(authors: Any) -> str:
    if isinstance(authors, list) and authors:
        return ", ".join(str(author) for author in authors if str(author).strip()) or "未获取"
    if isinstance(authors, str) and authors:
        return authors
    return "未获取"


def field(value: Any) -> str:
    if value is None:
        return "未获取"
    text = str(value).strip()
    if not text or text.casefold() in {"missing", "none", "null", "nan"}:
        return "未获取"
    return text


def format_topics(value: Any) -> str:
    if isinstance(value, list) and value:
        return ", ".join(str(item) for item in value)
    if isinstance(value, str) and value.strip():
        return value
    return "未获取"


def empty_digest_message(mode: str) -> str:
    if mode == "weekly":
        return "本周暂无符合筛选条件的高质量期刊论文。"
    return "暂无符合筛选条件的高质量期刊论文。"
