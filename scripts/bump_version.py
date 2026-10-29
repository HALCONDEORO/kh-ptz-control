#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Detecta el nivel de bump de versión a partir del mensaje de commit
y actualiza el archivo VERSION automáticamente.

Reglas:
  major  — BREAKING CHANGE, breaking:, major:, o ! tras el tipo (feat!, fix!...)
  minor  — feat:, feature:, minor:
  patch  — fix:, docs:, test:, chore:, refactor:, perf:, style:, build:, ci:
           o cualquier otro mensaje sin prefijo especial
"""
import re
import subprocess
import sys
from pathlib import Path

_MAJOR = re.compile(
    r'BREAKING[- ]CHANGE'
    r'|^(breaking|major)\s*(\(.+?\))?!?:',
    re.IGNORECASE | re.MULTILINE,
)
_MAJOR_BANG = re.compile(
    r'^(feat|fix|refactor|perf|style|docs|test|chore|build|ci)\s*(\(.+?\))?!:',
    re.IGNORECASE | re.MULTILINE,
)
_MINOR = re.compile(
    r'^(feat|feature|minor)\s*(\(.+?\))?:',
    re.IGNORECASE | re.MULTILINE,
)
_SKIP = re.compile(
    r'^Merge\b|^chore: bump version\b',
    re.IGNORECASE,
)


def detect_bump(msg: str) -> str:
    if _MAJOR.search(msg) or _MAJOR_BANG.search(msg):
        return 'major'
    if _MINOR.search(msg):
        return 'minor'
    return 'patch'


def bump(version: str, level: str) -> str:
    major, minor, patch = map(int, version.split('.'))
    if level == 'major':
        return f'{major + 1}.0.0'
    if level == 'minor':
        return f'{major}.{minor + 1}.0'
    return f'{major}.{minor}.{patch + 1}'


def main() -> None:
    if len(sys.argv) < 2:
        print('uso: bump_version.py <ruta-fichero-mensaje>', file=sys.stderr)
        sys.exit(1)

    msg = Path(sys.argv[1]).read_text(encoding='utf-8')

    if _SKIP.match(msg):
        return

    root = Path(__file__).parent.parent
    version_file = root / 'VERSION'

    if not version_file.exists():
        print('VERSION no encontrado, se omite el bump', file=sys.stderr)
        return

    current = version_file.read_text(encoding='utf-8').strip()
    level = detect_bump(msg)
    new_version = bump(current, level)

    version_file.write_text(new_version + '\n', encoding='utf-8')
    subprocess.run(['git', 'add', str(version_file)], check=True)

    print(f'  version {current} -> {new_version}  ({level})')


if __name__ == '__main__':
    main()
