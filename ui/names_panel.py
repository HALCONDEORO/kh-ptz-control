#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# names_panel.py — Panel de asistentes y lista de asistentes
#
# Extraído de widgets.py para reducir el tamaño de ese módulo.
#
# Clases:
#   NamesListWidget — QListWidget con reordenamiento interno + arrastre externo
#   NamesPanel      — panel flotante compacto con lista editable de asistentes

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ui.widgets import DragDropButton


def _get_text(parent, title: str, label: str, text: str = '') -> tuple[str, bool]:
    dlg = QInputDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setLabelText(label)
    dlg.setTextValue(text)
    dlg.setWindowModality(Qt.WindowModal)
    ok = dlg.exec_() == QDialog.Accepted
    return dlg.textValue(), ok

_EDIT_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'edit.svg')


# ─────────────────────────────────────────────────────────────────────────────
# _NameRow — widget de fila con nombre + botón editar inline
# ─────────────────────────────────────────────────────────────────────────────

class _NameRow(QWidget):
    """Fila de un asistente: nombre + botones ✏ y 🗑 a la derecha."""

    _BTN_EDIT_SS = (
        "QPushButton { background: #e8f5e9; border: 1px solid #a5d6a7;"
        " border-radius: 3px; font: bold 11px; color: #2e7d32; padding: 1px 4px; }"
        "QPushButton:pressed  { background: #c8e6c9; }"
        "QPushButton:disabled { background: #f0f0f0; color: #aaa; border-color: #ddd; }"
    )
    _BTN_DEL_SS = (
        "QPushButton { background: #ffebee; border: 1px solid #ef9a9a;"
        " border-radius: 3px; font: bold 11px; color: #c62828; padding: 1px 4px; }"
        "QPushButton:pressed  { background: #ffcdd2; }"
        "QPushButton:disabled { background: #f0f0f0; color: #aaa; border-color: #ddd; }"
    )

    def __init__(self, name: str, edit_cb, delete_cb, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 1, 4, 1)
        lay.setSpacing(3)

        lbl = QLabel(name)
        lbl.setStyleSheet("font: bold 12px; color: #222;")
        lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(lbl)

        self._edit_btn = QPushButton()
        self._edit_btn.setIcon(QIcon(_EDIT_ICON))
        self._edit_btn.setIconSize(QSize(15, 15))
        self._edit_btn.setFixedSize(26, 22)
        self._edit_btn.setFocusPolicy(Qt.NoFocus)
        self._edit_btn.setStyleSheet(self._BTN_EDIT_SS)
        self._edit_btn.clicked.connect(lambda: edit_cb(name))
        lay.addWidget(self._edit_btn)

        self._del_btn = QPushButton("Del")
        self._del_btn.setFixedSize(32, 22)
        self._del_btn.setFocusPolicy(Qt.NoFocus)
        self._del_btn.setStyleSheet(self._BTN_DEL_SS)
        self._del_btn.clicked.connect(lambda: delete_cb(name))
        lay.addWidget(self._del_btn)

    def set_enabled(self, enabled: bool) -> None:
        self._edit_btn.setEnabled(enabled)
        self._del_btn.setEnabled(enabled)


# ─────────────────────────────────────────────────────────────────────────────
# NamesListWidget — lista de asistentes con doble modo de arrastre
# ─────────────────────────────────────────────────────────────────────────────

class NamesListWidget(QListWidget):
    """
    Lista de asistentes que soporta dos tipos de drag simultáneamente:

    1. REORDENAMIENTO INTERNO: arrastra un nombre arriba/abajo dentro del panel.
       Detectado porque event.source() == self.

    2. ARRASTRE EXTERNO (a botones de asiento): MIME text/plain con CopyAction
       → el ítem permanece en la lista tras soltarlo sobre un asiento.

    SEÑAL order_changed(list):
      Emitida tras cada reordenamiento. NamesPanel la conecta para persistir.
    """

    order_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

        self._dragging_row: Optional[int] = None
        self._reorder_locked = False
        self._edit_cb = None
        self._delete_cb = None

        self.setStyleSheet("""
            QListWidget {
                background: white; border: 1px solid #ccc;
                border-radius: 4px; outline: none;
            }
            QListWidget::item {
                padding: 4px 8px; border-bottom: 1px solid #eee;
                font: bold 12px; color: #222;
            }
            QListWidget::item:selected {
                background: #e3f2fd; color: #1565C0; border-bottom-color: #bbdefb;
            }
            QListWidget::item:hover:!selected { background: #f1f8e9; }
        """)

    def populate(self, names: list, edit_cb=None, delete_cb=None) -> None:
        """Recarga la lista completa con botones ✏🗑 inline en cada fila."""
        self._edit_cb = edit_cb
        self._delete_cb = delete_cb
        self.clear()
        for name in names:
            item = QListWidgetItem('')          # texto vacío: evita doble texto
            item.setData(Qt.UserRole, name)     # nombre guardado en UserRole
            item.setSizeHint(QSize(0, 34))
            self.addItem(item)
            row = _NameRow(name, edit_cb or (lambda n: None), delete_cb or (lambda n: None))
            self.setItemWidget(item, row)

    def set_rows_enabled(self, enabled: bool) -> None:
        for i in range(self.count()):
            w = self.itemWidget(self.item(i))
            if isinstance(w, _NameRow):
                w.set_enabled(enabled)

    def startDrag(self, _supported_actions):
        """
        Override para poner el nombre como text/plain (DragDropButton lo acepta)
        y para guardar _dragging_row (dropEvent lo usa para reordenar).
        CopyAction: el ítem permanece en la lista al soltar sobre un asiento.
        Solo activo en modo SET; en modo CALL el drag externo está bloqueado.
        """
        item = self.currentItem()
        if item is None:
            return
        if DragDropButton._call_mode:
            return
        self._dragging_row = self.row(item)

        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setText(item.data(Qt.UserRole) or '')
        drag.setMimeData(mime)

        rect = self.visualItemRect(item)
        drag.setPixmap(self.viewport().grab(rect))
        drag.setHotSpot(QtCore.QPoint(rect.width() // 2, rect.height() // 2))

        drag.exec_(Qt.CopyAction | Qt.MoveAction)
        self._dragging_row = None

    def dragEnterEvent(self, event):
        """Solo acepta drags internos (reorden). Rechaza drops externos."""
        if event.source() is self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.source() is self:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Reordenamiento interno: mueve ítem de src_row a target_row."""
        if event.source() is not self or self._dragging_row is None:
            event.ignore()
            return
        if self._reorder_locked:
            event.ignore()
            return

        target_item = self.itemAt(event.pos())
        target_row  = self.row(target_item) if target_item is not None else self.count()
        src_row     = self._dragging_row

        if src_row == target_row:
            event.ignore()
            return

        name = self.item(src_row).data(Qt.UserRole) or ''
        self.takeItem(src_row)
        if src_row < target_row:
            target_row -= 1
        new_item = QListWidgetItem('')
        new_item.setData(Qt.UserRole, name)
        new_item.setSizeHint(QSize(0, 34))
        self.insertItem(target_row, new_item)
        row_w = _NameRow(name, self._edit_cb or (lambda n: None), self._delete_cb or (lambda n: None))
        self.setItemWidget(new_item, row_w)
        self.setCurrentRow(target_row)

        self.order_changed.emit([self.item(i).data(Qt.UserRole) for i in range(self.count())])
        event.acceptProposedAction()


# ─────────────────────────────────────────────────────────────────────────────
# NamesPanel — panel flotante compacto con lista editable de asistentes
# ─────────────────────────────────────────────────────────────────────────────

class NamesPanel(QWidget):
    """
    Panel semitransparente: x=1255, y=65, w=220, h=430. Arrastrable por toda la ventana.

    on_changed_cb — Callable de MainWindow:
      Firma: on_changed_cb(old_name=None, new_name=None)
      sin args → lista cambia (add/delete)
      con args → renombrado; MainWindow actualiza botones afectados
    """

    PX, PY, PW, PH = 1255, 65, 220, 730

    def __init__(self, names_list: list, on_changed_cb, clear_all_cb, parent=None,
                 recall_by_name_cb=None, undo_cb=None):
        super().__init__(parent)
        self.names              = names_list
        self._on_changed        = on_changed_cb
        self._clear_all_cb      = clear_all_cb
        self._recall_by_name_cb = recall_by_name_cb
        self._undo_cb           = undo_cb
        self._drag_pos          = None
        self._filter            = ""
        self._edit_mode         = False

        self.setGeometry(self.PX, self.PY, self.PW, self.PH)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "NamesPanel {"
            "  background: rgba(240,240,240,242);"
            "  border: 2px solid #999; border-radius: 6px;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)

        self._title = QLabel("👥 Attendees")
        self._title.setStyleSheet("font: bold 12px; color: #333;")
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)

        hint = QLabel("Drag to seat · drag back to unassign\nDouble-tap seat to clear")
        hint.setStyleSheet("font: 9px; color: #666;")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # Búsqueda: filtra la lista en vivo (A1) y, con Enter en modo Call,
        # lleva la cámara al asiento de esa persona (B3 — recall por nombre).
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍 Search · Enter = go to seat")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(26)
        self._search.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #bbb;"
            " border-radius: 3px; font: 11px; padding: 2px 6px; color: #222; }"
            "QLineEdit:focus { border-color: #1976d2; }"
        )
        self._search.textChanged.connect(self._on_search_changed)
        self._search.returnPressed.connect(self._on_search_enter)
        layout.addWidget(self._search)

        self._list = NamesListWidget()
        self._list.order_changed.connect(self._on_order_changed)
        layout.addWidget(self._list, stretch=1)

        _btn_style = (
            "QPushButton { background: white; border: 1px solid #bbb;"
            " border-radius: 3px; font: bold 11px; padding: 3px 4px; text-align: left; }"
            "QPushButton:pressed  { background: #ddd; }"
            "QPushButton:disabled { background: #f0f0f0; color: #aaa; border-color: #ddd; }"
        )

        self._edit_buttons = []
        for label, slot in [
            ("＋ Add", self._add_name),
            ("↩ Undo last assignment", self._undo),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(26)
            b.setStyleSheet(_btn_style)
            b.clicked.connect(slot)
            layout.addWidget(b)
            self._edit_buttons.append(b)

        btn_clear = QPushButton("🔄 Bring All Back")
        btn_clear.setFixedHeight(26)
        btn_clear.setStyleSheet(
            "QPushButton { background: white; border: 1px solid #1976d2;"
            " border-radius: 3px; font: bold 11px; color: #1565c0; padding: 3px 4px; text-align: left; }"
            "QPushButton:pressed  { background: #e3f2fd; }"
            "QPushButton:disabled { background: #f0f0f0; color: #aaa; border-color: #ddd; }"
        )
        btn_clear.clicked.connect(self._clear_all)
        layout.addWidget(btn_clear)
        self._edit_buttons.append(btn_clear)

        self._assigned: set = set()
        self._rebuild()
        self.set_edit_mode(False)  # Call es el modo por defecto
        self.setAcceptDrops(True)

    # ── Drop desde asientos (desasignar) ──────────────────────────────────────

    def dragEnterEvent(self, event):
        if DragDropButton._call_mode:
            event.ignore()
            return
        if event.mimeData().hasText():
            event.setDropAction(Qt.MoveAction)
            event.accept()

    def dragMoveEvent(self, event):
        if DragDropButton._call_mode:
            event.ignore()
            return
        if event.mimeData().hasText():
            event.setDropAction(Qt.MoveAction)
            event.accept()

    def dropEvent(self, event):
        if DragDropButton._call_mode:
            event.ignore()
            return
        name = event.mimeData().text().strip()
        if name:
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    # ─────────────────────────────────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        """
        Call (False): botones CRUD deshabilitados, reordenamiento bloqueado, drag desactivado.
        Set  (True):  todo habilitado, drag activo.
        """
        self._edit_mode = enabled
        self._list._reorder_locked = not enabled
        for btn in self._edit_buttons:
            btn.setEnabled(enabled)
        self._list.set_rows_enabled(enabled)

    def set_assigned(self, assigned: set):
        """Actualiza nombres asignados y refresca la lista visible."""
        self._assigned = assigned
        self._rebuild()

    def _rebuild(self):
        """Muestra los nombres NO asignados, en orden alfabético, aplicando el filtro de búsqueda."""
        f = self._filter.casefold()
        visible = sorted(
            (n for n in self.names
             if n not in self._assigned and (not f or f in n.casefold())),
            key=str.casefold,
        )
        self._list.populate(
            visible,
            edit_cb=self._edit_name_direct,
            delete_cb=self._delete_name_direct,
        )
        self._list.set_rows_enabled(not self._list._reorder_locked)
        self._update_title()

    def _update_title(self):
        """Título con contador sentados/total (A3)."""
        total = len(self.names)
        seated = len(self._assigned)
        self._title.setText(f"👥 Attendees  ({seated}/{total} seated)")

    # ── Búsqueda (A1) + recall por nombre (B3) ─────────────────────────────────

    def _on_search_changed(self, text: str):
        self._filter = text.strip()
        self._rebuild()

    def _on_search_enter(self):
        """
        Enter en la caja de búsqueda:
          · En modo Call → lleva la cámara al asiento de esa persona (B3).
          · En modo Set  → solo filtra (Enter no recupera para no mover en edición).
        """
        query = self._search.text().strip()
        if not query or self._edit_mode:
            return
        if self._recall_by_name_cb is not None:
            self._recall_by_name_cb(query)

    def _undo(self):
        """Deshace la última asignación de asiento (A2)."""
        if self._undo_cb is not None:
            self._undo_cb()

    def _on_order_changed(self, new_order: list):
        """
        Reconstruye self.names in-place preservando los nombres asignados
        (no aparecen en new_order porque están ocultos en la lista).
        """
        visible_iter = iter(new_order)
        reconstructed = [
            name if name in self._assigned else next(visible_iter)
            for name in self.names
        ]
        self.names[:] = reconstructed
        self._on_changed()

    def _add_name(self):
        text, ok = _get_text(self, "Add Name", "Full name:")
        if not (ok and text.strip()):
            return
        name = text.strip()
        if name in self.names:
            QMessageBox.information(self, "Duplicate Name", f'"{name}" already exists.')
            return
        self.names.append(name)
        self.names.sort(key=str.casefold)
        self._on_changed()
        self._rebuild()

    def _delete_name_direct(self, name: str):
        """Elimina el nombre pasado directamente (llamado desde el botón 🗑 inline)."""
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f'Remove "{name}" from the list?\n'
            "(Seats keep the assigned name until cleared with double-tap.)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.names.remove(name)
            self._on_changed()
            self._rebuild()

    def _edit_name_direct(self, old_name: str):
        """Edita el nombre pasado directamente (llamado desde el botón ✏ inline)."""
        new_name, ok = _get_text(self, "Edit Name", "New name:", text=old_name)
        if not (ok and new_name.strip()):
            return
        new_name = new_name.strip()
        if new_name == old_name:
            return
        if new_name in self.names:
            QMessageBox.information(self, "Duplicate Name", f'"{new_name}" already exists.')
            return
        try:
            self.names[self.names.index(old_name)] = new_name
        except ValueError:
            logger.warning("names_panel: old_name %r not found in list during rename", old_name)
            return
        self.names.sort(key=str.casefold)
        self._on_changed(old_name=old_name, new_name=new_name)
        self._rebuild()

    # ── Arrastre del panel ────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _clear_all(self):
        """
        Dispara borrado de todas las asignaciones.
        MainWindow ejecuta el borrado real; aquí solo se confirma y delega.
        """
        if not self._assigned:
            return
        n = len(self._assigned)
        reply = QMessageBox.question(
            self, "Bring All Back",
            f"Bring all {n} seated attendee{'s' if n != 1 else ''} back to the panel?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._clear_all_cb()
