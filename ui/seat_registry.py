"""Stable widget lookup, with unambiguous legacy preset aliases.

IDs, labels and camera memories are deliberately separate. Preset zero is
unassigned and never becomes an alias. A preset shared by cameras cannot be
looked up without a stable ID.
"""
from __future__ import annotations


class SeatRegistry:
    def __init__(self):
        self.by_id = {}
        self._presets = {}

    def add(self, seat, button):
        if seat.id in self.by_id:
            raise ValueError('Duplicate seat ID')
        self.by_id[seat.id] = button
        if seat.preset > 0:
            self._presets.setdefault(seat.preset, []).append(button)

    def get(self, seat_id):
        return self.by_id.get(str(seat_id))

    def legacy(self, preset):
        buttons = self._presets.get(preset, [])
        return buttons[0] if len(buttons) == 1 else None


def seat_button(window, seat_id):
    """Resolve a name-assignment key, retaining old platform attributes."""
    registry = getattr(window, '_seat_registry', None)
    if isinstance(registry, SeatRegistry):
        button = registry.get(seat_id)
        if button is not None:
            return button
    return getattr(window, f'Seat{seat_id}', None)
