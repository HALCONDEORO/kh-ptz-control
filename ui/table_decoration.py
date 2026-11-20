# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Fixed auditorium table decoration, separated from the main window."""
from PyQt5.QtWidgets import QLabel


def build_table_decoration(parent):
    table = QLabel(parent)
    table.setGeometry(96, 900, 245, 50)
    table.setStyleSheet(
        "background-color: rgba(100, 80, 60, 120);"
        "border: 2px solid rgba(70, 50, 30, 200);"
        "border-radius: 4px;"
    )
    return table
