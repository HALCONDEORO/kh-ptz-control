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


def test_synthetic_registry_visual(shell, tmp_path):
    root, _, _, app = shell
    root.resize(480, 260)
    root.setWindowTitle('Synthetic stable-ID seat test, no cameras')
    root.show()
    app.processEvents()
    assert root.grab().save(str(tmp_path / 'stable-seat-qt-synthetic.png'))


def test_legacy_name_assignment_clear_and_restart_cannot_resurrect(shell,monkeypatch):
    from ui.seat_names_mixin import SeatNamesController
    root, _, _, _ = shell
    root._seat_names={'17':'Old Person'}
    root._names_list=['Old Person','New Person']
    root._names_panel=SimpleNamespace(set_assigned=lambda _:None)
    writes=[]
    monkeypatch.setattr('ui.seat_names_mixin.save_names_data',lambda names,seats:writes.append(dict(seats)))
    ctrl=SeatNamesController(root)
    root._seat_names_ctrl=ctrl
    ctrl._restore_seat_names()
    assert root._seat_names=={'id-c':'Old Person'}
    root.Seat17.set_name('New Person')
    assert root._seat_names=={'id-c':'New Person'}
    root.Seat17.set_name('')
    assert root._seat_names=={}
    ctrl._restore_seat_names()
    assert root.Seat17.assigned_name==''
    assert writes[-1]=={}
    assert ctrl.undo_last_assignment()
    assert root._seat_names=={'id-c':'New Person'}


def test_name_recall_ambiguous_numeric_alias_cannot_fallback(shell):
    from ui.main_window import MainWindow
    from ui.seat_registry import SeatRegistry
    root, _, calls, _ = shell
    root._seat_registry=SeatRegistry()
    root._seat_registry.add(SimpleNamespace(id='a',preset=17),object())
    root._seat_registry.add(SimpleNamespace(id='b',preset=17),object())
    del root.Seat17
    root._seat_names={'17':'Legacy Person'}
    MainWindow._recall_seat_by_name(root,'Legacy Person')
    assert calls==[]


def test_fixed_platform_name_recall_keeps_legacy_path(shell):
    from ui.main_window import MainWindow
    root, _, _, _ = shell
    calls=[]
    root._seat_names={'1':'Platform Person'}
    root.Seat1=object()
    root._dispatch_preset_action=lambda preset,gesture:calls.append(preset)
    MainWindow._recall_seat_by_name(root,'Platform Person')
    assert calls==[1]


@pytest.mark.parametrize('key',['0','-1','50'])
def test_orphan_numeric_names_never_recall_hidden_memory(shell,key):
    from ui.main_window import MainWindow
    root,_,calls,_=shell
    root._seat_names={key:'Orphan'}
    MainWindow._recall_seat_by_name(root,'Orphan')
    assert calls==[]


@pytest.mark.parametrize('seat_id,preset',[('chair-clash',1),('1',17),('left-clash',2),('132',17)])
def test_layout_platform_collisions_rejected_before_widget_creation(shell,seat_id,preset):
    from ui.main_window import MainWindow
    from domain.room_layout import SeatLayout
    from PyQt5.QtWidgets import QPushButton
    root,_,_,_=shell
    before=root.findChildren(QPushButton)
    root._layout_svc.visible_seats=lambda:[SeatLayout(seat_id,'X',preset,'comments',60,100)]
    with pytest.raises(ValueError,match='fixed platform'):
        MainWindow._build_seat_buttons(root)
    assert root.findChildren(QPushButton)==before


@pytest.mark.parametrize('label',['',None,12])
def test_initial_ordinary_label_fallback_matches_clear(shell,label):
    from ui.main_window import MainWindow
    from domain.room_layout import SeatLayout
    root,_,_,_=shell
    root._layout_svc.visible_seats=lambda:[SeatLayout('fallback',label,17,'comments',60,100)]
    MainWindow._build_seat_buttons(root)
    button=root._seat_registry.get('fallback')
    assert button.text()=='17'
    button.set_name('')
    assert button.text()=='17'


def test_platform_widgets_exist_before_name_restore():
    import ast
    from pathlib import Path
    source=ast.parse(Path('ui/main_window.py').read_text())
    method=next(n for n in ast.walk(source) if isinstance(n,ast.FunctionDef) and n.name=='_build_ui')
    calls=[n.func.attr for statement in method.body for n in ast.walk(statement)
           if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
    assert calls.index('_build_platform_icons')<calls.index('_restore_seat_names')
