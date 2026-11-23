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
        self._ids_by_preset = {}

    def add(self, seat, button):
        if seat.id in self.by_id:
            raise ValueError("Duplicate seat ID")
        self.by_id[seat.id] = button
        if seat.preset > 0:
            self._presets.setdefault(seat.preset, []).append(button)
            self._ids_by_preset.setdefault(seat.preset, []).append(seat.id)

    def get(self, seat_id):
        return self.by_id.get(str(seat_id))

    def legacy(self, preset):
        buttons = self._presets.get(preset, [])
        return buttons[0] if len(buttons) == 1 else None

    def canonical_key(self, key):
        key = str(key)
        if key in self.by_id:
            return key
        try:
            ids = self._ids_by_preset.get(int(key), [])
        except ValueError:
            return key
        return ids[0] if len(ids) == 1 else key

    def canonical_names(self, names):
        # Exact stable IDs win a conflict with their old numeric preset alias.
        # Ambiguous aliases stay in storage, unbound, for explicit repair.
        result = {
            str(key): value for key, value in names.items() if self.canonical_key(key) == str(key)
        }
        for key, value in names.items():
            result.setdefault(self.canonical_key(key), value)
        return result


def seat_button(window, seat_id):
    """Resolve a name-assignment key, retaining old platform attributes."""
    registry = getattr(window, "_seat_registry", None)
    if isinstance(registry, SeatRegistry):
        button = registry.get(seat_id)
        if button is not None:
            return button
        canonical = registry.canonical_key(seat_id)
        if canonical != str(seat_id):
            return registry.get(canonical)
        try:
            if int(seat_id) in registry._presets:
                return None
        except (ValueError, TypeError):
            pass
    return getattr(window, f"Seat{seat_id}", None)
