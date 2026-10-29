# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests de enlaces internos en documentación Markdown.

El objetivo es detectar enlaces rotos dentro del repositorio sin depender de internet.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Detecta enlaces Markdown normales: [texto](ruta).
# La comprobación (?<!!) evita capturar imágenes: ![alt](ruta).
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")

# Elimina bloques fenced para no validar ejemplos de documentación como enlaces reales.
FENCED_CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)

# Elimina código inline para no validar ejemplos como `[texto](ruta)`.
INLINE_CODE_PATTERN = re.compile(r"`[^`\n]+`")

MARKDOWN_DIRS_TO_SKIP = {
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    ".env",
    "build",
    "dist",
    ".claude",
}

EXTERNAL_SCHEMES = {"http", "https", "mailto"}


def iter_markdown_files() -> list[Path]:
    """Devuelve archivos Markdown del repo que deben validarse."""
    files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*.md"):
        if any(part in MARKDOWN_DIRS_TO_SKIP for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def strip_non_content_code(markdown: str) -> str:
    """Elimina código fenced e inline para evitar falsos positivos."""
    without_blocks = FENCED_CODE_BLOCK_PATTERN.sub("", markdown)
    return INLINE_CODE_PATTERN.sub("", without_blocks)


def normalise_markdown_url(raw_url: str) -> str:
    """Devuelve la parte de ruta de un enlace Markdown local."""
    return raw_url.split("#", 1)[0].split("?", 1)[0].strip()


def is_external_or_anchor(raw_url: str) -> bool:
    """Ignora URLs externas, anchors puros y referencias vacías."""
    stripped = raw_url.strip()
    if not stripped or stripped.startswith("#"):
        return True

    parsed = urlparse(stripped)
    return parsed.scheme in EXTERNAL_SCHEMES


def target_path_for(markdown_file: Path, raw_url: str) -> Path | None:
    """Convierte un enlace Markdown relativo en una ruta local comprobable."""
    if is_external_or_anchor(raw_url):
        return None

    clean_url = normalise_markdown_url(raw_url)
    if not clean_url:
        return None

    candidate = Path(unquote(clean_url))

    if candidate.is_absolute():
        return PROJECT_ROOT / candidate.relative_to(candidate.anchor)

    return (markdown_file.parent / candidate).resolve()


def format_target_for_error(target: Path) -> str:
    """Formatea rutas para errores legibles en CI."""
    if target.is_relative_to(PROJECT_ROOT):
        return target.relative_to(PROJECT_ROOT).as_posix()
    return str(target)


def test_markdown_internal_links_point_to_existing_files() -> None:
    violations: list[str] = []

    for markdown_file in iter_markdown_files():
        content = strip_non_content_code(markdown_file.read_text(encoding="utf-8"))
        for match in MARKDOWN_LINK_PATTERN.finditer(content):
            raw_url = match.group(2)
            target = target_path_for(markdown_file, raw_url)
            if target is None:
                continue

            if not target.exists():
                relative_file = markdown_file.relative_to(PROJECT_ROOT).as_posix()
                relative_target = format_target_for_error(target)
                violations.append(f"{relative_file}: enlace roto -> {raw_url!r} ({relative_target})")

    assert not violations, "Enlaces Markdown internos rotos:\n" + "\n".join(violations)
