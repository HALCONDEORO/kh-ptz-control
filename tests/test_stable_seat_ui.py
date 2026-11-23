"""Real Qt widgets, synthetic records, no camera/worker construction."""
from types import SimpleNamespace
import pytest
from conftest import ensure_real_qt


@pytest.fixture
def shell():
    ensure_real_qt()
    from PyQt5.QtWidgets import QApplication, QWidget
    from ui.main_window import MainWindow
    from domain.room_layout import SeatLayout
    app = QApplication.instance() or QApplication([])
    root = QWidget()
    assignments, calls = [], []
    seats = [SeatLayout('id-a', 'A', 0, 'comments', 80, 100),
             SeatLayout('id-b', 'B', 0, 'comments', 180, 100),
             SeatLayout('id-c', 'C', 17, 'comments', 280, 100)]
    root._layout_svc = SimpleNamespace(visible_seats=lambda: seats, seat_by_id=lambda key: next((s for s in seats if s.id==key),None))
    root._dispatch_layout_seat = lambda key, gesture: MainWindow._dispatch_layout_seat(root, key, gesture)
    root._dispatch_preset_action = lambda preset, gesture, **kw: calls.append((preset,kw['seat_id']))
    root._seat_names_ctrl = SimpleNamespace(
        _on_seat_name_assigned=lambda key, name: assignments.append((key, name)))
    root._call_preset_from_button = lambda preset: calls.append(preset)
    root._confirm_and_set_preset = lambda preset: calls.append(preset)
    MainWindow._build_seat_buttons(root)
    yield root, assignments, calls, app
    root.close()
    root.deleteLater()


def test_unassigned_buttons_are_distinct_and_cannot_dispatch(shell):
    root, _, calls, _ = shell
    a, b = root._seat_registry.get('id-a'), root._seat_registry.get('id-b')
    assert a is not b
    assert (a.text(), b.text()) == ('A', 'B')
    a._call_cb(0)
    b._set_cb(0)
    assert calls == []
    assert not hasattr(root, 'Seat0')


def test_name_signal_uses_stable_id_and_label_survives_clear(shell):
    root, assignments, _, _ = shell
    a = root._seat_registry.get('id-a')
    a.set_name('Synthetic Person')
    a.set_name('')
    assert assignments == [('id-a', 'Synthetic Person'), ('id-a', '')]
    assert a.text() == 'A'


def test_assigned_legacy_preset_alias_is_preserved(shell):
    root, _, calls, _ = shell
    assert root.Seat17 is root._seat_registry.get('id-c')
    root.Seat17._call_cb(17)
    assert calls == [(17, 'id-c')]


def test_synthetic_registry_visual(shell):
    root, _, _, app = shell
    root.resize(480, 260)
    root.setWindowTitle('Synthetic stable-ID seat test, no cameras')
    root.show()
    app.processEvents()
    assert root.grab().save('/downloads/kh-stable-seat-qt-synthetic.png')
