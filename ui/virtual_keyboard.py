# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""virtual_keyboard.py — Teclado virtual flotante para PyQt5 (pantalla táctil)."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QApplication, QSizePolicy, QLineEdit,
)
from PyQt5.QtCore import Qt, QObject, QEvent, QTimer


# ─── Mapa de teclas ───────────────────────────────────────────────────────────

_ROWS: list[list[str]] = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '⌫'],
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '↵'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', '.'],
    ['⇧', 'z', 'x', 'c', 'v', 'b', 'n', 'm', '-', '@'],
]

_SHIFT_MAP: dict[str, str] = {
    '1': '!', '2': '"', '3': '#', '4': '$', '5': '%',
    '6': '&', '7': '/', '8': '(', '9': ')', '0': '=',
    '.': ':', '-': '_', '@': '~',
}

# ─── Estilos ──────────────────────────────────────────────────────────────────

_SS_KEY = """
QPushButton {
    background: #f5f5f5;
    border: 1px solid #bbb;
    border-radius: 6px;
    font-size: 20px;
    font-family: 'Inter Tight', 'Segoe UI';
    color: #222;
}
QPushButton:pressed { background: #bdd3ff; border-color: #5588dd; }
"""

_SS_SPECIAL = """
QPushButton {
    background: #ccd8ea;
    border: 1px solid #99aabb;
    border-radius: 6px;
    font-size: 18px;
    font-family: 'Inter Tight', 'Segoe UI';
    color: #333;
}
QPushButton:pressed { background: #99bbdd; }
"""

_SS_SHIFT_ON = """
QPushButton {
    background: #4A7A44;
    border: 1px solid #2E5229;
    border-radius: 6px;
    font-size: 18px;
    font-family: 'Inter Tight', 'Segoe UI';
    color: white;
}
QPushButton:pressed { background: #2E5229; }
"""

_SS_CONTAINER = "background: #dde3ec; border-radius: 12px; border: 1px solid #aab;"


# ─── Widget ───────────────────────────────────────────────────────────────────

class VirtualKeyboard(QWidget):
    """Teclado QWERTY flotante que escribe en el QLineEdit con foco activo."""

    _KEY_H = 58
    _KEY_W = 68
    _SPECIAL_W = 96

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus,
        )
        self._target: QLineEdit | None = None
        self._shift = False
        self._letter_btns: dict[str, QPushButton] = {}
        self._shift_btn: QPushButton | None = None
        self._build_ui()

    # ── Construcción de UI ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(5)
        root.setContentsMargins(10, 10, 10, 10)

        for row in _ROWS:
            root.addLayout(self._build_row(row))

        # Fila de espacio
        space_row = QHBoxLayout()
        space_row.setSpacing(5)
        space_btn = self._btn('SPACE', special=True)
        space_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        space_btn.setFixedHeight(self._KEY_H)
        space_btn.clicked.connect(lambda: self._on_key(' '))
        space_row.addWidget(space_btn)
        root.addLayout(space_row)

        self.setStyleSheet(_SS_CONTAINER)

    def _build_row(self, chars: list[str]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(5)
        row.addStretch(1)
        for ch in chars:
            special = ch in ('⌫', '↵', '⇧')
            b = self._btn(ch, special=special)
            b.setFixedWidth(self._SPECIAL_W if special else self._KEY_W)
            b.setFixedHeight(self._KEY_H)
            b.clicked.connect(lambda _checked=False, c=ch: self._on_key(c))
            if ch == '⇧':
                self._shift_btn = b
            elif not special:
                self._letter_btns[ch] = b
            row.addWidget(b)
        row.addStretch(1)
        return row

    def _btn(self, label: str, *, special: bool = False) -> QPushButton:
        b = QPushButton(label)
        b.setFocusPolicy(Qt.NoFocus)
        b.setStyleSheet(_SS_SPECIAL if special else _SS_KEY)
        return b

    # ── Lógica de teclas ─────────────────────────────────────────────────────

    def _clear_target(self) -> None:
        """Limpia el objetivo cuando Qt destruye el QLineEdit asociado."""
        self._target = None
        self.hide()

    def _on_key(self, ch: str) -> None:
        if ch == '⌫':
            if self._target:
                try:
                    self._target.backspace()
                except RuntimeError:
                    self._target = None
            return
        if ch == '↵':
            if self._target:
                try:
                    self._target.returnPressed.emit()
                except RuntimeError:
                    self._target = None
            self.hide()
            return
        if ch == '⇧':
            self._shift = not self._shift
            self._update_shift()
            return
        if not self._target:
            return

        char = ch
        if self._shift:
            char = _SHIFT_MAP.get(ch, ch.upper())
            self._shift = False
            self._update_shift()

        try:
            self._target.insert(char)
        except RuntimeError:
            self._target = None

    def _update_shift(self) -> None:
        if self._shift_btn:
            self._shift_btn.setStyleSheet(_SS_SHIFT_ON if self._shift else _SS_SPECIAL)
        for ch, btn in self._letter_btns.items():
            btn.setText(_SHIFT_MAP.get(ch, ch.upper()) if self._shift else ch)

    # ── Posicionamiento y visibilidad ─────────────────────────────────────────

    def show_for(self, widget: QLineEdit) -> None:
        if self._target is not None:
            try:
                self._target.destroyed.disconnect(self._clear_target)
            except (RuntimeError, TypeError):
                pass
        self._target = widget
        widget.destroyed.connect(self._clear_target)
        if not self.isVisible():
            self._reposition()
            self.show()

    def _reposition(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        x = (screen.width() - self.width()) // 2 + screen.x()
        y = screen.bottom() - self.height() - 10
        self.move(x, y)


# ─── Event filter ─────────────────────────────────────────────────────────────

class _KeyboardFilter(QObject):

    def __init__(self, keyboard: VirtualKeyboard) -> None:
        super().__init__(QApplication.instance())
        self._kb = keyboard
        # Un solo timer reutilizable: FocusIn lo para, FocusOut lo (re)arranca.
        # Evita la acumulación de QTimer.singleShot que causaba ocultaciones espurias.
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(250)
        self._hide_timer.timeout.connect(self._maybe_hide)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if isinstance(obj, QLineEdit):
            if event.type() == QEvent.FocusIn:
                self._hide_timer.stop()
                self._kb.show_for(obj)
            elif event.type() == QEvent.FocusOut:
                self._hide_timer.start()
        return False

    def _maybe_hide(self) -> None:
        if not isinstance(QApplication.focusWidget(), QLineEdit):
            self._kb.hide()


# ─── API pública ──────────────────────────────────────────────────────────────

def install_virtual_keyboard(app: QApplication) -> VirtualKeyboard:
    """Instala el teclado virtual global. Llamar una sola vez tras crear QApplication."""
    kb = VirtualKeyboard()
    app.installEventFilter(_KeyboardFilter(kb))
    return kb
