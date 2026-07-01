from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from journal_config import load_yaml_file

try:
    import requests
except ImportError:  # pragma: no cover - local minimal environments
    requests = None

try:
    import yaml
except ImportError:  # pragma: no cover - local minimal environments
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILES = [ROOT / "config" / "journals_zh.yml", ROOT / "config" / "journals_en.yml"]
REPORT_PATH = ROOT / "logs" / "journal_metadata_resolution_report.md"
USER_AGENT = "academic-literature-alert/0.1"


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    all_journals: list[dict[str, Any]] = []
    config_by_path: dict[Path, dict[str, Any]] = {}
    for path in CONFIG_FILES:
        config = load_yaml(path)
        config_by_path[path] = config
        for journal in config.get("journals", []):
            all_journals.append(journal)

    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    for journal in all_journals:
        if not journal.get("enabled", True):
            continue
        result = resolve_journal(journal)
        if result["status"] == "resolved_openalex":
            apply_resolution(journal, result["source"])
            resolved.append({"name": journal.get("name", ""), "source": result["source"]})
        elif result["status"] == "ambiguous":
            mark_unresolved(journal, "OpenAlex source ambiguous; verify ISSN/source_id manually.")
            ambiguous.append({"name": journal.get("name", ""), "candidates": result.get("candidates", [])})
        else:
            mark_unresolved(journal, "OpenAlex source unresolved; verify ISSN/source_id manually.")
            unresolved.append({"name": journal.get("name", ""), "candidates": result.get("candidates", [])})

    if yaml is not None:
        for path, config in config_by_path.items():
            write_yaml(path, config)
    write_report(total=len(all_journals), resolved=resolved, unresolved=unresolved, ambiguous=ambiguous)


def load_yaml(path: Path) -> dict[str, Any]:
    return load_yaml_file(path, yaml)


def write_yaml(path: Path, config: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False, width=120)


def resolve_journal(journal: dict[str, Any]) -> dict[str, Any]:
    if requests is None:
        return {"status": "unresolved", "candidates": [], "reason": "requests is not installed"}
    for identifier in [journal.get("openalex_source_id"), journal.get("source_id")]:
        source_id = normalize_openalex_id(str(identifier or ""))
        if source_id:
            source = get_openalex_source(source_id)
            if source:
                return {"status": "resolved_openalex", "source": source}

    for identifier in [journal.get("issn"), journal.get("eissn")]:
        if identifier:
            source = get_openalex_source_by_issn(str(identifier))
            if source:
                return {"status": "resolved_openalex", "source": source}

    names = [journal.get("name", "")] + list(journal.get("aliases") or [])
    for name in [str(value).strip() for value in names if str(value).strip()]:
        candidates = search_openalex_sources(name)
        exact = [source for source in candidates if normalize_name(source.get("display_name", "")) == normalize_name(name)]
        if len(exact) == 1:
            return {"status": "resolved_openalex", "source": exact[0]}
        if len(exact) > 1:
            return {"status": "ambiguous", "candidates": summarize_sources(exact)}
        if len(candidates) > 1:
            return {"status": "ambiguous", "candidates": summarize_sources(candidates)}
        if len(candidates) == 1:
            candidate = candidates[0]
            if high_confidence_match(name, candidate):
                return {"status": "resolved_openalex", "source": candidate}
            return {"status": "unresolved", "candidates": summarize_sources(candidates)}
    return {"status": "unresolved", "candidates": []}


def get_openalex_source(source_id: str) -> dict[str, Any] | None:
    url = f"https://api.openalex.org/sources/{normalize_openalex_id(source_id)}"
    response = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def get_openalex_source_by_issn(issn: str) -> dict[str, Any] | None:
    normalized = normalize_issn(issn)
    if not normalized:
        return None
    response = requests.get(f"https://api.openalex.org/sources/issn:{normalized}", timeout=20, headers={"User-Agent": USER_AGENT})
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def search_openalex_sources(query: str) -> list[dict[str, Any]]:
    response = requests.get(
        "https://api.openalex.org/sources",
        params={"search": query, "per-page": 5},
        timeout=20,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.json().get("results", [])


def apply_resolution(journal: dict[str, Any], source: dict[str, Any]) -> None:
    issns = source.get("issn") or []
    journal["issn"] = first_issn(issns) or journal.get("issn", "")
    journal["eissn"] = second_issn(issns) or journal.get("eissn", "")
    source_id = normalize_openalex_id(source.get("id", ""))
    journal["openalex_source_id"] = source_id
    journal["source_id"] = source_id
    journal["resolved_display_name"] = source.get("display_name", "")
    journal["metadata_status"] = "resolved_openalex"
    if not journal.get("metadata_note"):
        journal["metadata_note"] = "OpenAlex source resolved; journal quality still requires manual verification."


def mark_unresolved(journal: dict[str, Any], note: str) -> None:
    for field in ["issn", "eissn", "openalex_source_id", "source_id"]:
        journal[field] = journal.get(field, "") or ""
    journal["metadata_status"] = "unresolved"
    journal["metadata_note"] = note


def write_report(
    total: int,
    resolved: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
    note: str = "",
) -> None:
    lines = [
        "# Journal Metadata Resolution Report",
        "",
        f"- total_journals: {total}",
        f"- resolved_count: {len(resolved)}",
        f"- unresolved_count: {len(unresolved)}",
        f"- ambiguous_count: {len(ambiguous)}",
    ]
    if note:
        lines.extend(["", f"> {note}"])
    lines.extend(["", "## Resolved", ""])
    if resolved:
        for item in resolved:
            source = item.get("source", {})
            lines.append(f"- {item.get('name')}: {source.get('display_name', '')} ({normalize_openalex_id(source.get('id', ''))})")
    else:
        lines.append("- None")
    lines.extend(["", "## Unresolved", ""])
    if unresolved:
        for item in unresolved:
            lines.append(f"- {item.get('name')}")
            append_candidates(lines, item.get("candidates", []))
    else:
        lines.append("- None")
    lines.extend(["", "## Ambiguous", ""])
    if ambiguous:
        for item in ambiguous:
            lines.append(f"- {item.get('name')}")
            append_candidates(lines, item.get("candidates", []))
    else:
        lines.append("- None")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_candidates(lines: list[str], candidates: list[dict[str, Any]]) -> None:
    if not candidates:
        lines.append("  - candidates: none")
        return
    lines.append("  - candidates:")
    for candidate in candidates[:5]:
        lines.append("    - " + json.dumps(candidate, ensure_ascii=False))


def summarize_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "display_name": source.get("display_name", ""),
            "id": normalize_openalex_id(source.get("id", "")),
            "issn": source.get("issn", []),
            "works_count": source.get("works_count", 0),
        }
        for source in sources
    ]


def high_confidence_match(name: str, source: dict[str, Any]) -> bool:
    display = str(source.get("display_name", ""))
    return normalize_name(display) == normalize_name(name)


def normalize_name(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def normalize_openalex_id(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("https://openalex.org/"):
        return text.rsplit("/", 1)[-1]
    return text


def normalize_issn(value: str) -> str:
    return str(value or "").strip().upper().replace("-", "")


def first_issn(values: list[str]) -> str:
    return str(values[0]) if values else ""


def second_issn(values: list[str]) -> str:
    return str(values[1]) if len(values) > 1 else ""


if __name__ == "__main__":
    main()
