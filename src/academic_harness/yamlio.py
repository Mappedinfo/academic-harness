from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError:
        data = _parse_minimal_yaml(text)
    else:
        data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def dump_yaml(data: dict[str, Any]) -> str:
    return "\n".join(_dump_lines(data, 0)) + "\n"


def _dump_lines(value: Any, indent: int) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_dump_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {_format_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(_dump_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}- {_format_scalar(item)}")
        return lines
    return [f"{prefix}{_format_scalar(value)}"]


def _format_scalar(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text or text.strip() != text or any(ch in text for ch in [":", "#", "{", "}", "[", "]"]):
        return json.dumps(text, ensure_ascii=False)
    return text


def _parse_minimal_yaml(text: str) -> dict[str, Any]:
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [(indent, content) for indent, content in lines if content]
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise ValueError("Could not parse complete YAML document")
    if not isinstance(value, dict):
        raise ValueError("Top-level YAML must be a mapping")
    return value


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if lines[index][1].startswith("-"):
        return _parse_list(lines, index, indent)
    return _parse_map(lines, index, indent)


def _parse_map(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ValueError(f"Unexpected indentation near: {content}")
        if content.startswith("-"):
            break
        if ":" not in content:
            raise ValueError(f"Expected key/value line near: {content}")
        key, raw_value = content.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        index += 1
        if raw_value:
            result[key] = _parse_scalar(raw_value)
        elif index < len(lines) and lines[index][0] > current_indent:
            result[key], index = _parse_block(lines, index, lines[index][0])
        else:
            result[key] = None
    return result, index


def _parse_list(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent or not content.startswith("-"):
            break
        if current_indent > indent:
            raise ValueError(f"Unexpected indentation near: {content}")
        item = content[1:].strip()
        index += 1
        if item:
            if ":" in item and not item.startswith(("'", '"')):
                key, raw_value = item.split(":", 1)
                item_map: dict[str, Any] = {key.strip(): _parse_scalar(raw_value.strip()) if raw_value.strip() else None}
                if index < len(lines) and lines[index][0] > current_indent:
                    nested, index = _parse_map(lines, index, lines[index][0])
                    item_map.update(nested)
                result.append(item_map)
            else:
                result.append(_parse_scalar(item))
        elif index < len(lines) and lines[index][0] > current_indent:
            nested, index = _parse_block(lines, index, lines[index][0])
            result.append(nested)
        else:
            result.append(None)
    return result, index


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return json.loads(value) if value.startswith('"') else value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _clean_line(line: str) -> tuple[int, str]:
    stripped = line.lstrip(" ")
    indent = len(line) - len(stripped)
    if not stripped or stripped.startswith("#"):
        return indent, ""
    return indent, _strip_comment(stripped.rstrip())


def _strip_comment(value: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(value):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or value[index - 1].isspace():
                return value[:index].rstrip()
    return value
