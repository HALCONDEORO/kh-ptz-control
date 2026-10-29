#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_digital_joystick.py — adapters/input/joystick.py had no coverage
#
# The DigitalJoystick replaced the 8-arrow button pad, so it is now the only way
# an operator drives a camera by hand. tests/test_input_adapters.py covers
# joystick_adapter.py (the gamepad), never this widget. The behaviour that
# decides whether a camera is controllable:
#
#   - the dead zone must stop the camera. A drift of a few pixels near the centre
#     that keeps issuing moves means a camera that never quite stops.
#   - sector hysteresis: dragging along a diagonal boundary must not flip the
#     direction back and forth, which on real hardware is a visible stutter.
#   - release must always call stop_handler. A missed stop leaves a camera panning
#     until something else interrupts it — the worst failure this widget has.
#   - the zoom ring maps position to 0–100% and must clamp, never wrap: a ring
#     drag that jumps from 100 to 0 slams the lens across its whole range.

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PyQt5")

from conftest import ensure_real_qt        # noqa: E402

SIZE = 200            # widget is square; radius 100
CENTER = 100.0


@pytest.fixture(scope="module", autouse=True)
def _real_qt():
    ensure_real_qt()


@pytest.fixture
def qapp(_real_qt):
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


class _Handlers(dict):
    """Records every (direction, pan_spd, tilt_spd) the joystick asks for."""

    def __init__(self):
        super().__init__()
        self.calls: list[tuple[str, int, int]] = []
        for name in ("up", "down", "left", "right",
                     "upleft", "upright", "downleft", "downright"):
            self[name] = self._make(name)

    def _make(self, name):
        def _handler(pan_spd, tilt_spd):
            self.calls.append((name, pan_spd, tilt_spd))
        return _handler

    @property
    def directions(self) -> list[str]:
        return [c[0] for c in self.calls]


@pytest.fixture
def joystick(qapp):
    """A joystick with recording handlers, plus its stop counter."""
    from PyQt5.QtWidgets import QWidget

    from adapters.input.joystick import DigitalJoystick

    # Qt owns the child; if the parent is only a local it is collected as soon
    # as the factory returns and the joystick's C++ object goes with it.
    parents = []

    def _make(speed_provider=None):
        parent = QWidget()
        parents.append(parent)
        handlers = _Handlers()
        stops = []
        widget = DigitalJoystick(
            parent, 0, 0, SIZE, handlers, lambda: stops.append(1),
            speed_provider=speed_provider,
        )
        return widget, handlers, stops

    yield _make
    parents.clear()


def point(dx: float, dy: float):
    """A QPoint dx/dy pixels from the widget centre (screen axes: +y is down)."""
    from PyQt5.QtCore import QPoint
    return QPoint(int(CENTER + dx), int(CENTER + dy))


def drag(widget, dx: float, dy: float):
    """Press (or move, if already tracking) the knob to an offset."""
    if widget._tracking:
        widget._process(point(dx, dy))
    else:
        widget._tracking = True
        widget._process(point(dx, dy))


class TestConstruction:
    def test_geometry_is_applied(self, joystick):
        widget, handlers, stops = joystick()
        assert widget.width() == SIZE and widget.height() == SIZE

    def test_the_repeat_timer_is_not_running_at_rest(self, joystick):
        """A timer ticking before any input would move the camera on its own."""
        widget, handlers, stops = joystick()
        assert not widget._timer.isActive()

    def test_the_repeat_interval_matches_the_visca_cadence(self, joystick):
        widget, handlers, stops = joystick()
        assert widget._timer.interval() == 150

    def test_the_knob_starts_centred(self, joystick):
        widget, handlers, stops = joystick()
        assert widget._knob_pos == widget._center

    def test_the_default_speed_ceiling_is_the_configured_one(self, joystick):
        from config import SPEED_MAX
        widget, handlers, stops = joystick()
        assert widget._speed_provider() == SPEED_MAX

    def test_a_speed_provider_overrides_the_default(self, joystick):
        widget, handlers, stops = joystick(speed_provider=lambda: 7)
        assert widget._speed_provider() == 7


class TestDeadZone:
    def test_no_movement_inside_the_dead_zone(self, joystick):
        """Finger tremor on a touchscreen must not drive the camera."""
        widget, handlers, stops = joystick()
        drag(widget, 3, 0)
        assert handlers.calls == []

    def test_the_dead_zone_is_smaller_than_the_disc(self, joystick):
        widget, handlers, stops = joystick()
        assert 0 < widget._dead_r < widget._outer_r

    def test_returning_to_the_centre_stops_the_camera(self, joystick):
        """The move-back-and-hold case: without this the camera keeps panning
        while the finger rests in the middle."""
        widget, handlers, stops = joystick()
        drag(widget, 0, -60)             # up
        assert handlers.calls
        drag(widget, 0, 0)               # back to centre
        assert stops == [1]

    def test_returning_to_the_centre_stops_the_repeat_timer(self, joystick):
        widget, handlers, stops = joystick()
        drag(widget, 0, -60)
        drag(widget, 0, 0)
        assert not widget._timer.isActive()

    def test_a_dead_zone_touch_alone_does_not_call_stop(self, joystick):
        """Nothing was moving; a spurious stop would cancel another source."""
        widget, handlers, stops = joystick()
        drag(widget, 2, 2)
        assert stops == []


class TestDirections:
    @pytest.mark.parametrize("dx,dy,expected", [
        (0, -60, "up"),
        (60, 0, "right"),
        (0, 60, "down"),
        (-60, 0, "left"),
        (45, -45, "upright"),
        (45, 45, "downright"),
        (-45, 45, "downleft"),
        (-45, -45, "upleft"),
    ])
    def test_each_sector_calls_its_handler(self, joystick, dx, dy, expected):
        widget, handlers, stops = joystick()
        drag(widget, dx, dy)
        assert handlers.directions == [expected]

    def test_screen_axes_are_not_inverted(self, joystick):
        """Dragging up must tilt up; a sign slip here inverts every camera."""
        widget, handlers, stops = joystick()
        drag(widget, 0, -60)
        assert handlers.directions == ["up"]

    def test_all_eight_directions_are_reachable(self, joystick):
        widget, handlers, stops = joystick()
        assert set(widget._DIR_MAP.values()) == set(
            ("up", "upright", "right", "downright",
             "down", "downleft", "left", "upleft")
        )

    def test_holding_a_direction_does_not_resend_on_every_move(self, joystick):
        """Re-sending the same direction on each mouse-move floods the VISCA
        link; the repeat timer owns that cadence instead."""
        widget, handlers, stops = joystick()
        drag(widget, 0, -60)
        drag(widget, 0, -70)
        drag(widget, 0, -80)
        assert handlers.directions == ["up"]

    def test_the_repeat_timer_runs_while_a_direction_is_held(self, joystick):
        widget, handlers, stops = joystick()
        drag(widget, 0, -60)
        assert widget._timer.isActive()

    def test_a_timer_tick_repeats_the_held_direction(self, joystick):
        widget, handlers, stops = joystick()
        drag(widget, 0, -60)
        widget._on_timer_tick()
        assert handlers.directions == ["up", "up"]

    def test_a_timer_tick_after_release_sends_nothing(self, joystick):
        """A tick that outlives the drag would keep the camera moving."""
        widget, handlers, stops = joystick()
        drag(widget, 0, -60)
        widget._tracking = False
        widget._on_timer_tick()
        assert handlers.directions == ["up"]

    def test_changing_direction_sends_the_new_one(self, joystick):
        widget, handlers, stops = joystick()
        drag(widget, 0, -60)
        drag(widget, 60, 0)
        assert handlers.directions == ["up", "right"]


class TestHysteresis:
    def test_a_boundary_wobble_does_not_flip_direction(self, joystick):
        """Real fingers sit on a sector edge; flipping there is a visible
        camera stutter."""
        import math
        widget, handlers, stops = joystick()
        # Just inside 'up', then a hair past the up/upright boundary (22.5°).
        drag(widget, 0, -60)
        near_boundary = math.radians(22.5 + 5)      # inside the 10° hysteresis
        drag(widget, 60 * math.sin(near_boundary), -60 * math.cos(near_boundary))
        assert handlers.directions == ["up"]

    def test_a_decisive_move_past_the_boundary_does_switch(self, joystick):
        import math
        widget, handlers, stops = joystick()
        drag(widget, 0, -60)
        past = math.radians(22.5 + 15)              # beyond the hysteresis band
        drag(widget, 60 * math.sin(past), -60 * math.cos(past))
        assert handlers.directions == ["up", "upright"]

    def test_the_hysteresis_band_is_narrower_than_a_sector(self, joystick):
        """A band wider than the half-sector would make some directions
        unreachable once a neighbour is held."""
        widget, handlers, stops = joystick()
        assert 0 < widget._HYSTERESIS < widget._SECTOR_HALF


class TestSpeed:
    def test_a_small_deflection_is_the_slowest_speed(self, joystick):
        widget, handlers, stops = joystick(speed_provider=lambda: 20)
        drag(widget, 0, -(widget._dead_r + 1))
        assert handlers.calls[0][2] == 1

    def test_full_deflection_reaches_the_ceiling(self, joystick):
        widget, handlers, stops = joystick(speed_provider=lambda: 20)
        drag(widget, 0, -widget._outer_r)
        assert handlers.calls[0][2] == 20

    def test_speed_grows_with_deflection(self, joystick):
        widget, handlers, stops = joystick(speed_provider=lambda: 20)
        drag(widget, 0, -(widget._dead_r + 5))
        slow = handlers.calls[-1][2]
        drag(widget, 60, 0)                 # different sector, larger radius
        drag(widget, 0, -(widget._outer_r))
        fast = handlers.calls[-1][2]
        assert fast > slow

    def test_speed_never_drops_below_one(self, joystick):
        """Zero speed is 'stop' in VISCA — a move command with speed 0 is a
        command that does nothing."""
        widget, handlers, stops = joystick(speed_provider=lambda: 1)
        drag(widget, 0, -widget._outer_r)
        assert handlers.calls[0][1] >= 1
        assert handlers.calls[0][2] >= 1

    def test_a_diagonal_splits_speed_across_both_axes(self, joystick):
        widget, handlers, stops = joystick(speed_provider=lambda: 20)
        drag(widget, 45, -45)
        _, pan, tilt = handlers.calls[0]
        assert pan == tilt                          # 45° → equal components
        assert pan < 20                             # and below the ceiling

    def test_a_pure_tilt_barely_pans(self, joystick):
        widget, handlers, stops = joystick(speed_provider=lambda: 20)
        drag(widget, 0, -widget._outer_r)
        _, pan, tilt = handlers.calls[0]
        assert tilt == 20
        assert pan == 1

    def test_dragging_outside_the_disc_is_clamped(self, joystick):
        """A finger that leaves the widget must not produce a speed above the
        ceiling."""
        widget, handlers, stops = joystick(speed_provider=lambda: 20)
        drag(widget, 0, -500)
        assert handlers.calls[0][2] == 20

    def test_the_ceiling_is_read_at_each_move(self, joystick):
        """The operator can change the speed limit while dragging."""
        limit = {"value": 4}
        widget, handlers, stops = joystick(speed_provider=lambda: limit["value"])
        drag(widget, 0, -widget._outer_r)
        assert handlers.calls[-1][2] == 4
        limit["value"] = 20
        drag(widget, widget._outer_r, 0)          # full deflection, new ceiling
        assert handlers.calls[-1][1] == 20


class TestMouseEvents:
    # Offsets stay well inside the disc: the zoom arc sits at ~0.83·r and grabs
    # presses within its stroke tolerance, so a press further out would be read
    # as a ring drag rather than a PTZ move.
    def _event(self, dx, dy, button=None):
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QMouseEvent
        button = Qt.LeftButton if button is None else button
        return QMouseEvent(
            QMouseEvent.MouseButtonPress, point(dx, dy),
            button, button, Qt.NoModifier,
        )

    def test_press_starts_tracking_and_moves(self, joystick):
        widget, handlers, stops = joystick()
        widget.mousePressEvent(self._event(0, -40))
        assert widget._tracking
        assert handlers.directions == ["up"]

    def test_release_stops_the_camera(self, joystick):
        """The single most important behaviour in this widget."""
        widget, handlers, stops = joystick()
        widget.mousePressEvent(self._event(0, -40))
        widget.mouseReleaseEvent(self._event(0, -40))
        assert stops == [1]

    def test_release_recentres_the_knob(self, joystick):
        widget, handlers, stops = joystick()
        widget.mousePressEvent(self._event(0, -40))
        widget.mouseReleaseEvent(self._event(0, -40))
        assert widget._knob_pos == widget._center

    def test_release_stops_the_repeat_timer(self, joystick):
        widget, handlers, stops = joystick()
        widget.mousePressEvent(self._event(0, -40))
        widget.mouseReleaseEvent(self._event(0, -40))
        assert not widget._timer.isActive()

    def test_release_clears_the_held_direction(self, joystick):
        widget, handlers, stops = joystick()
        widget.mousePressEvent(self._event(0, -40))
        widget.mouseReleaseEvent(self._event(0, -40))
        assert widget._cur_dir is None
        assert widget._cur_sector is None

    def test_a_right_click_does_not_drive_the_camera(self, joystick):
        from PyQt5.QtCore import Qt
        widget, handlers, stops = joystick()
        widget.mousePressEvent(self._event(0, -40, button=Qt.RightButton))
        assert handlers.calls == []
        assert not widget._tracking

    def test_moving_without_pressing_does_nothing(self, joystick):
        widget, handlers, stops = joystick()
        widget.mouseMoveEvent(self._event(0, -40))
        assert handlers.calls == []

    def test_a_move_while_pressed_follows_the_finger(self, joystick):
        widget, handlers, stops = joystick()
        widget.mousePressEvent(self._event(0, -40))
        widget.mouseMoveEvent(self._event(40, 0))
        assert handlers.directions == ["up", "right"]


class TestZoomRing:
    def test_zoom_starts_at_zero(self, joystick):
        widget, handlers, stops = joystick()
        assert widget._ring_pct == 0.0

    def test_an_external_zoom_update_is_applied(self, joystick):
        """The camera reports its own zoom; the ring must follow without
        echoing a command back."""
        widget, handlers, stops = joystick()
        received = []
        widget.zoom_changed.connect(received.append)
        widget.set_zoom(42)
        assert widget._ring_pct == 42.0
        assert received == []

    @pytest.mark.parametrize("value,expected", [
        (-10, 0.0), (0, 0.0), (50, 50.0), (100, 100.0), (140, 100.0),
    ])
    def test_external_zoom_is_clamped(self, joystick, value, expected):
        widget, handlers, stops = joystick()
        widget.set_zoom(value)
        assert widget._ring_pct == expected

    def test_zoom_accepts_a_float_reading(self, joystick):
        widget, handlers, stops = joystick()
        widget.set_zoom(33.7)
        assert widget._ring_pct == pytest.approx(33.7)

    def test_the_left_end_of_the_arc_is_wide(self, joystick):
        widget, handlers, stops = joystick()
        assert widget._pos_to_ring_pct(point(-80, 0)) == pytest.approx(0.0)

    def test_the_right_end_of_the_arc_is_tele(self, joystick):
        widget, handlers, stops = joystick()
        assert widget._pos_to_ring_pct(point(80, 0)) == pytest.approx(100.0)

    def test_the_top_of_the_arc_is_the_midpoint(self, joystick):
        widget, handlers, stops = joystick()
        assert widget._pos_to_ring_pct(point(0, -80)) == pytest.approx(50.0)

    def test_the_lower_half_snaps_instead_of_wrapping(self, joystick):
        """Dragging off the bottom of the arc must clamp to the nearer end —
        wrapping would slam the lens across its whole range."""
        widget, handlers, stops = joystick()
        assert widget._pos_to_ring_pct(point(-80, 40)) == 0.0
        assert widget._pos_to_ring_pct(point(80, 40)) == 100.0

    def test_percentage_and_position_round_trip(self, joystick):
        widget, handlers, stops = joystick()
        for pct in (0.0, 25.0, 50.0, 75.0, 100.0):
            pos = widget._ring_pct_to_pos(pct)
            assert widget._pos_to_ring_pct(pos) == pytest.approx(pct, abs=0.01)

    def test_a_press_on_the_arc_grabs_the_ring_not_the_knob(self, joystick):
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QMouseEvent
        widget, handlers, stops = joystick()
        on_ring = widget._ring_pct_to_pos(50.0)
        event = QMouseEvent(QMouseEvent.MouseButtonPress, on_ring.toPoint(),
                            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        widget.mousePressEvent(event)
        assert widget._ring_dragging
        assert not widget._tracking
        assert handlers.calls == []              # no camera movement

    def test_dragging_the_ring_emits_the_new_zoom(self, joystick):
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QMouseEvent
        widget, handlers, stops = joystick()
        received = []
        widget.zoom_changed.connect(received.append)
        press = QMouseEvent(QMouseEvent.MouseButtonPress,
                            widget._ring_pct_to_pos(50.0).toPoint(),
                            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        widget.mousePressEvent(press)
        move = QMouseEvent(QMouseEvent.MouseMove,
                           widget._ring_pct_to_pos(75.0).toPoint(),
                           Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        widget.mouseMoveEvent(move)
        assert received[0] == 50
        assert received[-1] == 75

    def test_releasing_the_ring_emits_the_final_value(self, joystick):
        """The last emission is what the camera is left at."""
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QMouseEvent
        widget, handlers, stops = joystick()
        received = []
        widget.zoom_changed.connect(received.append)
        press = QMouseEvent(QMouseEvent.MouseButtonPress,
                            widget._ring_pct_to_pos(30.0).toPoint(),
                            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        widget.mousePressEvent(press)
        release = QMouseEvent(QMouseEvent.MouseButtonRelease,
                              widget._ring_pct_to_pos(30.0).toPoint(),
                              Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        widget.mouseReleaseEvent(release)
        assert widget._ring_dragging is False
        assert received[-1] == 30

    def test_releasing_the_ring_does_not_stop_the_camera(self, joystick):
        """A zoom drag is not a PTZ move; calling stop_handler here would cancel
        an unrelated movement."""
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QMouseEvent
        widget, handlers, stops = joystick()
        press = QMouseEvent(QMouseEvent.MouseButtonPress,
                            widget._ring_pct_to_pos(30.0).toPoint(),
                            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        widget.mousePressEvent(press)
        release = QMouseEvent(QMouseEvent.MouseButtonRelease,
                              widget._ring_pct_to_pos(30.0).toPoint(),
                              Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        widget.mouseReleaseEvent(release)
        assert stops == []

    def test_a_press_inside_the_disc_is_not_a_ring_hit(self, joystick):
        widget, handlers, stops = joystick()
        assert not widget._is_ring_hit(point(0, -20))

    def test_a_press_below_the_centre_is_not_a_ring_hit(self, joystick):
        """The arc is the upper semicircle only."""
        widget, handlers, stops = joystick()
        assert not widget._is_ring_hit(point(0, 83))


class TestColourMode:
    def test_platform_mode_uses_the_platform_palette(self, joystick):
        widget, handlers, stops = joystick()
        widget.set_mode("platform")
        assert widget._palette is widget._COLORS_SET
        assert widget._ring_active_color == widget._ring_platform_color

    def test_any_other_mode_uses_the_comments_palette(self, joystick):
        """The colour is how the operator tells which camera they are driving."""
        widget, handlers, stops = joystick()
        widget.set_mode("comments")
        assert widget._palette is widget._COLORS_CALL
        assert widget._ring_active_color == widget._ring_comments_color

    def test_the_glow_follows_the_palette(self, joystick):
        widget, handlers, stops = joystick()
        widget.set_mode("comments")
        assert widget._glow_grad is widget._glow_grads[id(widget._COLORS_CALL)]

    def test_switching_mode_does_not_move_the_camera(self, joystick):
        widget, handlers, stops = joystick()
        widget.set_mode("comments")
        assert handlers.calls == []
        assert stops == []

    def test_switching_mode_keeps_the_zoom_reading(self, joystick):
        widget, handlers, stops = joystick()
        widget.set_zoom(60)
        widget.set_mode("comments")
        assert widget._ring_pct == 60.0


class TestPainting:
    def test_the_widget_paints_without_error(self, joystick):
        """paintEvent runs on every timer tick and mouse move; an exception
        there floods the log and leaves the control blank."""
        from PyQt5.QtGui import QPaintEvent
        from PyQt5.QtCore import QRect
        widget, handlers, stops = joystick()
        widget.set_zoom(45)
        widget.paintEvent(QPaintEvent(QRect(0, 0, SIZE, SIZE)))

    def test_it_paints_while_a_direction_is_held(self, joystick):
        from PyQt5.QtGui import QPaintEvent
        from PyQt5.QtCore import QRect
        widget, handlers, stops = joystick()
        drag(widget, 45, -45)
        widget.paintEvent(QPaintEvent(QRect(0, 0, SIZE, SIZE)))

    def test_it_paints_in_the_comments_palette(self, joystick):
        from PyQt5.QtGui import QPaintEvent
        from PyQt5.QtCore import QRect
        widget, handlers, stops = joystick()
        widget.set_mode("comments")
        drag(widget, 0, -60)
        widget.paintEvent(QPaintEvent(QRect(0, 0, SIZE, SIZE)))
