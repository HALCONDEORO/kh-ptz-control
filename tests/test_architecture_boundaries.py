# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests de límites de arquitectura.

Estos tests aplican las reglas documentadas en docs/ARCHITECTURE.md.
Evitan importar módulos de la aplicación para poder ejecutarse sin PyQt,
cámaras, hardware ATEM ni servicios específicos de Raspberry Pi.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PYTHON_DIRS_TO_SKIP = {
    ".git",
    ".github",
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
}

# Las excepciones temporales deben ser pocas, explícitas y tener retirada trazable.
MAX_TEMPORARY_IMPORT_EXCEPTIONS = 0
ISSUE_REF_RE = re.compile(r"^#\d+$")


@dataclass(frozen=True)
class TemporaryImportException:
    reason: str
    removal_issues: tuple[str, ...]
    removal_plan: str


TEMPORARY_IMPORT_EXCEPTIONS: dict[str, dict[str, TemporaryImportException]] = {
    # No active temporary exceptions — architecture debt budget: 0/0.
}

DOMAIN_ROOTS = ("domain",)
APPLICATION_ROOTS = ("application",)
UI_ROOTS = ("ui",)
PORTS_ROOTS = ("ports",)

# Archivos UI que vivían en la raíz durante la migración Phase 2c.
# La migración está completa: todos residen ahora en ui/ y son escaneados
# por iter_python_files(*UI_ROOTS).  Lista mantenida vacía para no
# perder el historial de intención; existing_files() la ignora.
LEGACY_UI_FILES: tuple[str, ...] = ()

DOMAIN_FORBIDDEN_IMPORTS = {
    "PyQt5": "domain no debe depender de PyQt",
    "socket": "domain no debe hablar con la red directamente",
}

APPLICATION_FORBIDDEN_IMPORTS = {
    "PyQt5": "los servicios de application no deben depender de PyQt",
    # socket is allowed in application/ for diagnostics (camera_discovery, network_diagnostics).
    # Camera control sockets live in adapters/ (ViscaCameraAdapter). Do not add socket calls
    # to application-layer control-path files.
}

# ports/ defines interfaces — same rules as domain (no hardware, no Qt).
PORTS_FORBIDDEN_IMPORTS = {
    "PyQt5": "ports no debe depender de PyQt",
    "socket": "ports no debe hablar con la red directamente",
    "ptz.visca.commands": "ports no debe importar implementaciones VISCA concretas",
    "ptz.visca.protocol": "ports no debe importar implementaciones VISCA concretas",
    "ptz.visca.transport": "ports no debe importar implementaciones VISCA concretas",
}

UI_FORBIDDEN_IMPORTS = {
    "ptz.visca.commands": "la UI debe usar servicios de cámara, no builders VISCA de bajo nivel",
    "ptz.visca.controller": "la UI no debe importar ViscaController directamente; usar ApplicationController",
    "ptz.visca.protocol": "la UI debe usar servicios de cámara, no módulos VISCA de bajo nivel",
    "ptz.visca.transport": "la UI debe usar servicios de cámara, no transporte VISCA de bajo nivel",
    "visca_commands": "la UI debe usar servicios de cámara, no módulos VISCA legacy",
}

# ── Source-level guards (attribute-access and call patterns) ─────────────────
# These cannot be checked via import scanning; they require source-text scanning.
# Files listed here have known violations tracked in the linked issues.
# Remove a file from the exception set once its violations are fixed and confirmed.

# UI files with active `._visca.` attribute-access violations (migration pending).
# All ._visca. calls removed from main_window.py in #740; set is empty.
UI_VISCA_DIRECT_ACCESS_ALLOWED: dict[str, str] = {}

# UI files with raw VISCA socket implementations (migration pending).
UI_RAW_VISCA_SOCKET_ALLOWED: dict[str, str] = {
    "ui/splash_screen.py": "#740 — self-test uses raw VISCA socket until CameraPort self-test path exists",
}

DOMAIN_FORBIDDEN_FILE_METHODS = {
    "open",
    "read_text",
    "write_text",
    "read_bytes",
    "write_bytes",
}


def iter_python_files(*roots: str) -> list[Path]:
    """Devuelve archivos Python dentro de raíces existentes del repositorio."""
    files: set[Path] = set()

    for root_name in roots:
        root = PROJECT_ROOT / root_name
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if any(part in PYTHON_DIRS_TO_SKIP for part in path.parts):
                continue
            files.add(path)

    return sorted(files)


def existing_files(*relative_paths: str) -> list[Path]:
    """Devuelve archivos existentes desde rutas explícitas relativas al repositorio."""
    files = []
    for relative_path in relative_paths:
        path = PROJECT_ROOT / relative_path
        if path.exists():
            files.append(path)
    return sorted(files)


def iter_ui_boundary_files() -> list[Path]:
    """Devuelve archivos UI actuales y legacy que deben cumplir límites de UI."""
    return sorted(set(iter_python_files(*UI_ROOTS) + existing_files(*LEGACY_UI_FILES)))


def parse_python_file(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
                modules.update(f"{node.module}.{alias.name}" for alias in node.names)

    return modules


def matches_module(imported: str, forbidden: str) -> bool:
    return imported == forbidden or imported.startswith(f"{forbidden}.")


def exception_reason(path: Path, forbidden: str) -> str | None:
    relative = path.relative_to(PROJECT_ROOT).as_posix()
    exception = TEMPORARY_IMPORT_EXCEPTIONS.get(relative, {}).get(forbidden)
    return exception.reason if exception else None


def temporary_exception_count() -> int:
    return sum(len(exceptions) for exceptions in TEMPORARY_IMPORT_EXCEPTIONS.values())


def all_forbidden_imports() -> set[str]:
    return set().union(
        DOMAIN_FORBIDDEN_IMPORTS,
        APPLICATION_FORBIDDEN_IMPORTS,
        UI_FORBIDDEN_IMPORTS,
    )


def assert_no_forbidden_imports(
    files: list[Path],
    forbidden_imports: dict[str, str],
) -> None:
    violations: list[str] = []

    for path in files:
        tree = parse_python_file(path)
        imports = imported_modules(tree)

        for imported in imports:
            for forbidden, reason in forbidden_imports.items():
                if not matches_module(imported, forbidden):
                    continue
                exception = exception_reason(path, forbidden)
                if exception:
                    continue

                relative = path.relative_to(PROJECT_ROOT).as_posix()
                violations.append(f"{relative}: importa {imported!r} ({reason})")

    assert not violations, "Imports prohibidos por arquitectura:\n" + "\n".join(violations)


def called_file_methods(tree: ast.AST) -> set[str]:
    calls: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)

    return calls


def test_temporary_import_exception_budget_is_not_exceeded() -> None:
    count = temporary_exception_count()

    assert count <= MAX_TEMPORARY_IMPORT_EXCEPTIONS, (
        "Presupuesto de deuda de arquitectura superado: "
        f"{count}/{MAX_TEMPORARY_IMPORT_EXCEPTIONS} excepciones temporales. "
        "Retira una excepción existente o sube el presupuesto de forma explícita."
    )


def test_temporary_import_exceptions_are_traceable_and_current() -> None:
    violations: list[str] = []
    known_forbidden_imports = all_forbidden_imports()

    for relative_path, exceptions in TEMPORARY_IMPORT_EXCEPTIONS.items():
        path = PROJECT_ROOT / relative_path
        imports: set[str] = set()

        if not path.exists():
            violations.append(f"{relative_path}: la excepción apunta a un archivo inexistente")
        else:
            imports = imported_modules(parse_python_file(path))

        for forbidden, exception in exceptions.items():
            label = f"{relative_path}: {forbidden}"

            if forbidden not in known_forbidden_imports:
                violations.append(f"{label}: el import prohibido no existe en las reglas activas")

            if not exception.reason.strip():
                violations.append(f"{label}: falta motivo concreto")

            if not exception.removal_plan.strip():
                violations.append(f"{label}: falta plan de retirada")

            if not exception.removal_issues:
                violations.append(f"{label}: falta issue de retirada")

            invalid_issues = [
                issue for issue in exception.removal_issues
                if not ISSUE_REF_RE.fullmatch(issue)
            ]
            if invalid_issues:
                joined = ", ".join(invalid_issues)
                violations.append(f"{label}: issues de retirada inválidos: {joined}")

            if path.exists() and not any(matches_module(imported, forbidden) for imported in imports):
                violations.append(
                    f"{label}: excepción obsoleta; el archivo ya no importa ese módulo"
                )

    assert not violations, "Excepciones temporales inválidas:\n" + "\n".join(violations)


def test_application_layer_does_not_import_pyqt() -> None:
    assert_no_forbidden_imports(
        iter_python_files(*APPLICATION_ROOTS),
        APPLICATION_FORBIDDEN_IMPORTS,
    )


def test_domain_layer_has_no_pyqt_or_socket_imports() -> None:
    assert_no_forbidden_imports(
        iter_python_files(*DOMAIN_ROOTS),
        DOMAIN_FORBIDDEN_IMPORTS,
    )


def test_domain_layer_does_not_directly_read_or_write_files() -> None:
    violations: list[str] = []

    for path in iter_python_files(*DOMAIN_ROOTS):
        tree = parse_python_file(path)
        calls = called_file_methods(tree)
        forbidden_calls = calls.intersection(DOMAIN_FORBIDDEN_FILE_METHODS)

        if forbidden_calls:
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            joined = ", ".join(sorted(forbidden_calls))
            violations.append(f"{relative}: llamada directa a filesystem: {joined}")

    assert not violations, "Domain no debe leer/escribir archivos directamente:\n" + "\n".join(violations)


def test_ui_layer_does_not_import_low_level_visca_modules() -> None:
    assert_no_forbidden_imports(
        iter_ui_boundary_files(),
        UI_FORBIDDEN_IMPORTS,
    )


def test_ports_layer_has_no_hardware_or_qt_imports() -> None:
    assert_no_forbidden_imports(
        iter_python_files(*PORTS_ROOTS),
        PORTS_FORBIDDEN_IMPORTS,
    )


def test_ui_layer_does_not_access_visca_controller_directly() -> None:
    """UI must not call hardware methods via mw._visca.* attribute chains.

    Files listed in UI_VISCA_DIRECT_ACCESS_ALLOWED have active violations
    tracked in the linked issues. Any other UI file containing '._visca.'
    is a new violation and must not be introduced.
    """
    violations: list[str] = []

    for path in iter_ui_boundary_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if relative in UI_VISCA_DIRECT_ACCESS_ALLOWED:
            continue

        source = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "._visca." in line:
                violations.append(f"{relative}:{lineno}: {stripped[:90]}")

    assert not violations, (
        "Nuevas llamadas directas a ._visca.* en UI (no están en la lista de excepciones):\n"
        + "\n".join(violations)
    )


def test_ui_layer_does_not_use_raw_visca_socket() -> None:
    """UI must not implement raw VISCA TCP socket directly.

    Files listed in UI_RAW_VISCA_SOCKET_ALLOWED have active violations tracked
    in the linked issues. Any other UI file implementing _send_visca_cmd or
    opening a bare socket for VISCA is a new violation.
    """
    violations: list[str] = []

    for path in iter_ui_boundary_files():
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if relative in UI_RAW_VISCA_SOCKET_ALLOWED:
            continue

        source = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "_send_visca_cmd" in line:
                violations.append(f"{relative}:{lineno}: {stripped[:90]}")

    assert not violations, (
        "Nuevas implementaciones de socket VISCA raw en UI (no están en la lista de excepciones):\n"
        + "\n".join(violations)
    )
