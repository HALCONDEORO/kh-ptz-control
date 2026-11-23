#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# seat_names_mixin.py — Mixin para asignación y persistencia de nombres en asientos
#
# Responsabilidad: todos los callbacks que responden a drag-drop de nombres,
# cambios CRUD en NamesPanel, y restauración de nombres persistidos al arrancar.
#
# Accede en runtime a atributos de MainWindow:
#   self._names_list, self._seat_names, self._preset_svc
#   self._names_panel  (NamesPanel)
#   self._chairman_btn (ChairmanButton)
#   getattr(self, f"Seat{N}")  (GoButton / SpecialDragButton / ChairmanButton)

import logging
from typing import Optional

from config import save_names_data
from ui.widgets import GoButton, SpecialDragButton
from ui.seat_registry import seat_button

logger = logging.getLogger(__name__)


class SeatNamesController:

    _UNDO_DEPTH = 25

    def __init__(self, window):
        self._w = window
        # Pila de snapshots de _seat_names para deshacer asignaciones (A2).
        self._undo_stack: list[dict] = []

    def _push_undo(self):
        """Guarda una instantánea del estado de asientos antes de mutarlo."""
        self._undo_stack.append(dict(self._w._seat_names))
        if len(self._undo_stack) > self._UNDO_DEPTH:
            self._undo_stack.pop(0)

    def undo_last_assignment(self) -> bool:
        """Restaura el estado de asientos anterior a la última asignación/borrado (A2)."""
        if not self._undo_stack:
            return False
        prev = self._undo_stack.pop()
        for key in set(self._w._seat_names) | set(prev):
            name = prev.get(key, "")
            btn = seat_button(self._w, key)
            if isinstance(btn, (GoButton, SpecialDragButton)):
                btn.set_name(name, emit_signal=False)
        self._w._seat_names.clear()
        self._w._seat_names.update(prev)
        save_names_data(self._w._names_list, self._w._seat_names)
        self._sync_assigned_to_panel()
        return True

    def _restore_seat_names(self):
        for seat_str, name in self._w._seat_names.items():
            btn = seat_button(self._w, seat_str)
            if isinstance(btn, (GoButton, SpecialDragButton)) and name:
                # emit_signal=False: no mueve cámara ni persiste al arrancar
                btn.set_name(name, emit_signal=False)
        self._sync_assigned_to_panel()

    def _on_seat_name_assigned(self, seat_number: int | str, name: str):
        self._push_undo()
        key = str(seat_number)
        if name:
            # Exclusividad: un nombre solo puede estar en un asiento a la vez
            for other_key, other_name in list(self._w._seat_names.items()):
                if other_name == name and other_key != key:
                    other_btn = seat_button(self._w, other_key)
                    if isinstance(other_btn, (GoButton, SpecialDragButton)):
                        other_btn.set_name("", emit_signal=False)
                    del self._w._seat_names[other_key]
                    break
            self._w._seat_names[key] = name
        else:
            self._w._seat_names.pop(key, None)

        save_names_data(self._w._names_list, self._w._seat_names)
        self._sync_assigned_to_panel()

    def _on_names_list_changed(self, old_name: Optional[str] = None, new_name: Optional[str] = None):
        if old_name and new_name:
            # Undo changes seat positions, not the attendee's current name.
            # Migrate every saved position snapshot alongside the live map.
            for snapshot in self._undo_stack:
                for key, name in snapshot.items():
                    if name == old_name:
                        snapshot[key] = new_name
            for key, v in self._w._seat_names.items():
                if v == old_name:
                    self._w._seat_names[key] = new_name
                    btn = seat_button(self._w, key)
                    if isinstance(btn, (GoButton, SpecialDragButton)):
                        btn.set_name(new_name, emit_signal=False)

            # Migrar preset de Chairman si la persona renombrada tenía uno.
            # A missing preset and a failed disk save both return False.
            # Warn only if a preset existed. Keep the pending in-memory map;
            # the next whole-map save retries it (see persistence retry tests).
            had_preset = self._w._preset_svc.has_preset(old_name)
            persisted = self._w._preset_svc.rename(old_name, new_name)
            if had_preset and not persisted:
                logger.warning(
                    "Preset for '%s' renamed in memory but not saved to disk",
                    new_name,
                )
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self._w,
                    "Position preset not saved",
                    f'The saved camera position for "{new_name}" could not be '
                    "written to disk.\nIt may be lost when the app restarts; "
                    "save the position again to keep it.",
                )

        save_names_data(self._w._names_list, self._w._seat_names)

    def _sync_assigned_to_panel(self):
        """Pasa al NamesPanel el set actualizado de nombres asignados."""
        self._w._names_panel.set_assigned(set(self._w._seat_names.values()))

    def _clear_all_seats(self):
        """Borra todos los nombres asignados de los asientos."""
        self._push_undo()
        for key in list(self._w._seat_names.keys()):
            btn = seat_button(self._w, key)
            if isinstance(btn, (GoButton, SpecialDragButton)):
                btn.set_name("", emit_signal=False)
        self._w._seat_names.clear()
        save_names_data(self._w._names_list, self._w._seat_names)
        self._sync_assigned_to_panel()
