"""No hardware/Qt needed to test identity and alias rules."""
from types import SimpleNamespace
import pytest
from ui.seat_registry import SeatRegistry, seat_button


def test_unassigned_seats_keep_distinct_identity():
    registry = SeatRegistry()
    a, b = object(), object()
    registry.add(SimpleNamespace(id='uuid-a', preset=0), a)
    registry.add(SimpleNamespace(id='uuid-b', preset=0), b)
    assert registry.get('uuid-a') is a
    assert registry.get('uuid-b') is b
    assert registry.legacy(0) is None


def test_shared_preset_never_guesses_camera():
    registry = SeatRegistry()
    a, b = object(), object()
    registry.add(SimpleNamespace(id='a', preset=5), a)
    assert registry.legacy(5) is a
    registry.add(SimpleNamespace(id='b', preset=5), b)
    assert registry.legacy(5) is None
    assert registry.get('a') is a


def test_duplicate_identity_rejected():
    registry = SeatRegistry()
    seat = SimpleNamespace(id='a', preset=5)
    registry.add(seat, object())
    with pytest.raises(ValueError):
        registry.add(seat, object())


def test_legacy_platform_lookup_and_stable_key():
    registry = SeatRegistry()
    platform, custom = object(), object()
    registry.add(SimpleNamespace(id='uuid', preset=0), custom)
    window = SimpleNamespace(_seat_registry=registry, Seat1=platform)
    assert seat_button(window, 'uuid') is custom
    assert seat_button(window, '1') is platform
    assert seat_button(window, 'missing') is None
