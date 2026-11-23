"""Stable-ID widget wiring and name recall, separate from the window shell."""

import logging
from ui.widgets import GoButton
from ui.seat_builder import build_special_seat_button
from ui.seat_registry import SeatRegistry, seat_button
from domain.call_set_policy import InputType
from domain.preset import PLATFORM_PRESETS

logger = logging.getLogger(__name__)


def build_layout_seat_buttons(self):
    if self._layout_svc is None:
        logger.error("_build_seat_buttons: LayoutService not available — no seat buttons created")
        return
    seats = self._layout_svc.visible_seats()
    if any(
        seat.preset in PLATFORM_PRESETS or str(seat.id) in {str(p) for p in PLATFORM_PRESETS}
        for seat in seats
    ):
        raise ValueError("Layout seats conflict with fixed platform controls")
    self._seat_registry = SeatRegistry()
    for seat in seats:
        seat_number = seat.preset
        x, y = seat.x, seat.y
        if seat.type == "special" or seat_number in (128, 129, 130, 131):
            button = build_special_seat_button(seat_number, x, y, parent=self, label=seat.label)
            button.init_preset_actions(
                seat_number,
                call_cb=self._call_preset_from_button,
                set_cb=self._confirm_and_set_preset,
            )
        else:
            button = GoButton(seat_number, self)
            button.move(x, y)
            button.init_preset_actions(
                seat_number,
                call_cb=self._call_preset_from_button,
                set_cb=self._confirm_and_set_preset,
            )
        button._layout_seat_id = seat.id
        button._layout_label = seat.label
        if isinstance(button, GoButton):
            button.set_name("", emit_signal=False)
        button.name_assigned.connect(
            lambda _number, name, seat_id=seat.id: self._seat_names_ctrl._on_seat_name_assigned(
                seat_id, name
            )
        )
        self._seat_registry.add(seat, button)
        button._call_cb = lambda _preset, seat_id=seat.id: self._dispatch_layout_seat(
            seat_id, InputType.TAP
        )
        button._set_cb = lambda _preset, seat_id=seat.id: self._dispatch_layout_seat(
            seat_id, InputType.LONG_PRESS
        )
        if seat_number == 0:
            button.setToolTip("No camera memory assigned. Calibration required.")
    # Existing preset-based paths keep only unambiguous, assigned aliases.
    for preset in {seat.preset for seat in seats if seat.preset > 0}:
        button = self._seat_registry.legacy(preset)
        if button is not None:
            setattr(self, f"Seat{preset}", button)


def recall_layout_seat_by_name(self, query):
    """Recall por nombre (B3): lleva la cámara al asiento de la persona buscada.

    Coincidencia exacta (sin distinguir mayúsculas) primero; si no, subcadena.
    Sin coincidencia → no hace nada (la persona no está sentada en ningún asiento).
    """
    q = query.strip().casefold()
    if not q:
        return
    match_key = next((k for k, n in self._seat_names.items() if n.casefold() == q), None)
    if match_key is None:
        match_key = next((k for k, n in self._seat_names.items() if q in n.casefold()), None)
    if match_key is None:
        return
    button = seat_button(self, match_key)
    if button is not None and hasattr(button, "_layout_seat_id"):
        seat = self._layout_svc.seat_by_id(button._layout_seat_id)
        if seat is not None and seat.preset > 0:
            self._dispatch_layout_seat(seat.id, InputType.TAP)
        return
    registry = getattr(self, "_seat_registry", None)
    if isinstance(registry, SeatRegistry):
        try:
            if int(match_key) in registry._presets:
                return  # Unresolved/ambiguous layout alias, never guess.
        except ValueError:
            pass
    if isinstance(registry, SeatRegistry) and button is None:
        return  # Deleted/unbound seats are not a license to recall a memory.
    try:
        self._dispatch_preset_action(int(match_key), InputType.TAP)
    except ValueError:
        return


def dispatch_layout_seat(self, seat_id: str, input_type: InputType) -> None:
    seat = self._layout_svc.seat_by_id(seat_id)
    if seat is None or not seat.visible or seat.preset <= 0:
        return
    # Remaining SET/feedback paths are preset-based. Until they migrate,
    # reject ambiguous memories instead of choosing a camera or widget.
    if self._seat_registry.legacy(seat.preset) is None:
        return
    self._dispatch_preset_action(seat.preset, input_type, seat_id=seat.id)
