"""Reading and (minimal) writing of the ibc2.toml settings file."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_scalar(v) for v in value) + "]"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\n", "\n").replace("\r", "\r").replace("\t", "\t")
    return f'"{text}"'


def dumps(data: dict[str, Any]) -> str:
    """Serialise one level of tables (``{table: {key: scalar}}``) plus top-level scalars."""
    lines: list[str] = []
    for key, value in data.items():
        if not isinstance(value, dict):
            lines.append(f"{key} = {_scalar(value)}")
    for table, values in data.items():
        if isinstance(values, dict):
            if lines:
                lines.append("")
            lines.append(f"[{table}]")
            for key, value in values.items():
                if value is None:
                    continue
                lines.append(f"{key} = {_scalar(value)}")
    return "\n".join(lines) + "\n"


def save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(data), encoding="utf-8")
