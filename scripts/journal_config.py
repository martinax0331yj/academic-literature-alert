from __future__ import annotations

from pathlib import Path
from typing import Any


def load_yaml_file(path: Path, yaml_module: Any | None = None) -> dict[str, Any]:
    if yaml_module is not None:
        with path.open("r", encoding="utf-8") as handle:
            return yaml_module.safe_load(handle) or {}
    if path.name.startswith("journals_"):
        return load_journal_yaml_fallback(path)
    if path.name == "schedules.yml":
        return load_simple_nested_yaml_fallback(path)
    if path.name == "topics.yml":
        return load_topics_yaml_fallback(path)
    return {}


def load_journal_yaml_fallback(path: Path) -> dict[str, Any]:
    journals: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_discovery = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped == "journals:":
            continue
        if stripped.startswith("- "):
            if current:
                journals.append(current)
            current = {}
            in_discovery = False
            key, value = split_key_value(stripped[2:])
            if key:
                current[key] = parse_scalar(value)
            continue
        if current is None or ":" not in stripped:
            continue
        key, value = split_key_value(stripped)
        if not key:
            continue
        if key == "discovery" and value == "":
            current["discovery"] = {}
            in_discovery = True
            continue
        if in_discovery and raw_line.startswith("      "):
            current.setdefault("discovery", {})[key] = parse_scalar(value)
        else:
            in_discovery = False
            current[key] = parse_scalar(value)
    if current:
        journals.append(current)
    return {"journals": journals}


def split_key_value(text: str) -> tuple[str, str]:
    if ":" not in text:
        return "", ""
    key, value = text.split(":", 1)
    return key.strip(), value.strip()


def parse_scalar(value: str) -> Any:
    text = value.strip()
    if text == "":
        return ""
    if text in {"true", "True"}:
        return True
    if text in {"false", "False"}:
        return False
    if text == "[]":
        return []
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [strip_quotes(part.strip()) for part in inner.split(",")]
    return strip_quotes(text)


def strip_quotes(value: str) -> str:
    text = value.strip()
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    return text


def load_simple_nested_yaml_fallback(path: Path) -> dict[str, Any]:
    config: dict[str, Any] = {}
    current_section: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not raw_line.startswith(" ") and line.endswith(":"):
            current_section = line[:-1].strip()
            config[current_section] = {}
            continue
        stripped = line.strip()
        if current_section and ":" in stripped:
            key, value = split_key_value(stripped)
            if key and value != "":
                config[current_section][key] = parse_scalar(value)
    return config


def load_topics_yaml_fallback(path: Path) -> dict[str, Any]:
    config: dict[str, Any] = {"groups": {}}
    in_groups = False
    current_group: str | None = None
    current_list_key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0:
            in_groups = stripped == "groups:"
            current_group = None
            current_list_key = None
            continue
        if not in_groups:
            continue
        if indent == 2 and stripped.endswith(":"):
            current_group = stripped[:-1].strip()
            config["groups"][current_group] = {}
            current_list_key = None
            continue
        if current_group is None:
            continue
        if indent == 4 and ":" in stripped:
            key, value = split_key_value(stripped)
            if not key:
                continue
            if value == "":
                config["groups"][current_group][key] = []
                current_list_key = key
            else:
                config["groups"][current_group][key] = parse_scalar(value)
                current_list_key = None
            continue
        if indent >= 6 and stripped.startswith("- ") and current_list_key:
            config["groups"][current_group].setdefault(current_list_key, []).append(strip_quotes(stripped[2:].strip()))
    return config
