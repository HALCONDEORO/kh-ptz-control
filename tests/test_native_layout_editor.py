"""Native and web adapter share one transaction master, no cameras."""

import pytest
from conftest import ensure_real_qt
from application.web_layout_editor import WebLayoutEditor, EditorError


@pytest.fixture
def native(tmp_path):
    ensure_real_qt()
    from PyQt5.QtWidgets import QApplication
    from ui.native_layout_editor import NativeLayoutEditor

    app = QApplication.instance() or QApplication([])
    editor = WebLayoutEditor(tmp_path)
    editor.initialize()
    widget = NativeLayoutEditor(editor)
    yield widget, editor, app
    from PyQt5 import sip

    if not sip.isdeleted(widget):
        widget.dirty = False
        widget.close()


def test_native_saves_same_master_seen_by_web_adapter(native):
    widget, editor, _ = native
    widget.take()
    widget.create_block(6)
    assert len(widget.document["seats"]) == 84
    widget.save()
    assert len(editor.read("web-client")["document"]["seats"]) == 84
    with pytest.raises(EditorError) as error:
        editor.acquire("web-client")
    assert error.value.code == "editor_busy"
    widget.leave()
    assert editor.acquire("web-client")["generation"]


def test_web_writer_blocks_native_and_reload_shows_master(native):
    widget, editor, _ = native
    lease = editor.acquire("web-client")
    widget.run(widget.take)
    assert widget.generation is None
    current = editor.read("web-client")
    current["document"]["room_name"] = "From web client"
    editor.save("web-client", current["revision"], current["document"], lease["generation"])
    widget.load()
    assert widget.document["room_name"] == "From web client"


def test_undo_redo_remove_and_stable_ids(native):
    widget, _, _ = native
    widget.take()
    widget.add()
    identity = widget.document["seats"][0]["id"]
    widget.undo()
    assert widget.document["seats"] == []
    widget.redo()
    assert widget.document["seats"][0]["id"] == identity
    items = [item for item in widget.scene.items() if hasattr(item, "seat")]
    items[0].setSelected(True)
    widget.remove()
    assert widget.document["seats"] == []


def test_native_visual(native, tmp_path):
    widget, _, app = native
    widget.take()
    widget.create_block(6)
    widget.save()
    widget.show()
    app.processEvents()
    assert widget.grab().save(str(tmp_path / "native-layout-editor.png"))


def test_expired_turn_keeps_draft_and_stale_revision_rejected(native):
    widget, editor, _ = native
    widget.take()
    widget.add()
    editor._deadline = 0
    widget.run(widget.save)
    assert widget.generation is None
    assert widget.dirty
    assert len(widget.document["seats"]) == 1
    assert len(editor.read("web")["document"]["seats"]) == 0
    lease = editor.acquire("web")
    current = editor.read("web")
    current["document"]["room_name"] = "New web revision"
    editor.save("web", current["revision"], current["document"], lease["generation"])
    editor.release("web", lease["generation"])
    widget.take()
    widget.run(widget.save)
    assert "revision_conflict" in widget.status.text()
    assert editor.read("web")["document"]["room_name"] == "New web revision"


def test_locked_seat_cannot_move_or_delete(native):
    widget, _, app = native
    widget.take()
    widget.add()
    item = next(item for item in widget.scene.items() if hasattr(item, "seat"))
    item.setSelected(True)
    widget.locked.setChecked(True)
    widget.toggle_lock()
    item = next(item for item in widget.scene.items() if hasattr(item, "seat"))
    item.setSelected(True)
    widget.remove()
    assert len(widget.document["seats"]) == 1
    widget.move_seat(item, 200, 250)
    app.processEvents()
    assert widget.document["seats"][0]["x"] == 60


def test_shared_revision_refreshes_readonly_native(native):
    widget, editor, _ = native
    lease = editor.acquire("web")
    current = editor.read("web")
    current["document"]["room_name"] = "Shared update"
    editor.save("web", current["revision"], current["document"], lease["generation"])
    widget.refresh()
    assert widget.name.text() == "Shared update"


@pytest.mark.parametrize("exit_method", ["close", "reject", "accept", "done"])
def test_all_dialog_exit_paths_release_writer_and_timers(native, exit_method):
    widget, editor, _ = native
    widget.take()
    widget.show()
    if exit_method == "done":
        widget.done(1)
    else:
        getattr(widget, exit_method)()
    assert widget.generation is None
    assert not widget.timer.isActive()
    assert not widget.poll.isActive()
    assert editor.acquire("web-after-exit")["generation"]


def test_widget_destruction_releases_writer(native):
    from PyQt5 import sip

    widget, editor, _ = native
    widget.take()
    sip.delete(widget)
    assert editor.acquire("web-after-destroy")["generation"]


@pytest.mark.parametrize("exit_method", ["close", "reject", "accept", "done"])
def test_close_does_not_read_corrupt_master(native, exit_method):
    widget, editor, _ = native
    widget.take()
    editor.path.write_text("{corrupt")
    if exit_method == "done":
        widget.done(1)
    else:
        getattr(widget, exit_method)()
    assert widget.generation is None
    assert not widget.timer.isActive()
    assert not widget.poll.isActive()


def test_refusing_discard_keeps_visible_editor_and_turn(native, monkeypatch):
    widget, editor, _ = native
    widget.take()
    widget.add()
    monkeypatch.setattr(widget, "discard_ok", lambda: False)
    widget.accept()
    assert widget.generation is not None
    assert widget.timer.isActive()
    assert not widget._finalized
    assert editor.read(widget.session)["lease"] == "mine"


def test_release_failure_stops_timers_without_reading(native, monkeypatch):
    widget, editor, _ = native
    widget.take()

    def fail(*_):
        raise OSError("fixture release failed")

    monkeypatch.setattr(editor, "release", fail)
    widget.done(1)
    assert widget.generation is None
    assert not widget.timer.isActive()
    assert not widget.poll.isActive()


def test_escape_releases_turn(native):
    from PyQt5.QtTest import QTest
    from PyQt5.QtCore import Qt

    widget, editor, app = native
    widget.take()
    widget.show()
    app.processEvents()
    QTest.keyClick(widget, Qt.Key_Escape)
    assert widget.generation is None
    assert not widget.timer.isActive()
    assert editor.acquire("web-after-escape")["generation"]


def test_http_and_native_share_one_master(native):
    import json
    import threading
    import urllib.request
    from runtime.web_layout_editor import BoundedEditorServer, make_handler

    widget, editor, _ = native
    server = BoundedEditorServer(("127.0.0.1", 0), make_handler(editor, "unused"))
    origin = f"http://127.0.0.1:{server.server_port}"
    server.RequestHandlerClass = make_handler(editor, origin)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        first = urllib.request.urlopen(origin)
        cookie = first.headers["Set-Cookie"].split(";")[0]
        headers = {
            "Cookie": cookie,
            "X-KH-Editor": "1",
            "X-KH-Tab": "native-http-test-abcdefghijkl",
            "Origin": origin,
            "Content-Type": "application/json",
        }

        def request(path, data=None):
            return json.load(
                urllib.request.urlopen(
                    urllib.request.Request(
                        origin + "/api/" + path,
                        headers=headers,
                        data=None if data is None else json.dumps(data).encode(),
                    )
                )
            )

        widget.take()
        widget.create_block(6)
        widget.save()
        assert len(request("layout")["document"]["seats"]) == 84
        widget.leave()
        lease = request("lease", {})
        current = request("layout")
        current["document"]["room_name"] = "HTTP shared master"
        request(
            "save",
            dict(
                document=current["document"],
                revision=current["revision"],
                generation=lease["generation"],
            ),
        )
        widget.refresh()
        assert widget.document["room_name"] == "HTTP shared master"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_dialog_reopen_restarts_lifecycle_and_releases_second_turn(native):
    widget, editor, app = native
    widget.show()
    widget.take()
    widget.accept()
    widget.show()
    app.processEvents()
    assert widget.timer.isActive()
    assert not widget._finalized
    widget.take()
    widget.accept()
    assert editor.acquire("web-after-second-close")["generation"]
    assert not widget.timer.isActive()


def test_multi_selection_mouse_drag_is_one_persisted_undo_transaction(native):
    from PyQt5.QtCore import Qt, QPoint
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtTest import QTest

    widget, editor, app = native
    widget.show()
    widget.take()
    widget.create_block(1)
    widget.save()
    app.processEvents()
    items = sorted(
        [item for item in widget.scene.items() if hasattr(item, "seat")],
        key=lambda item: item.seat["column"],
    )
    a, b = items[:2]
    before = [(seat["x"], seat["y"]) for seat in widget.document["seats"]]
    history = len(widget.history)
    a.setSelected(True)
    b.setSelected(True)
    start = widget.view.mapFromScene(a.sceneBoundingRect().center())
    end = start + QPoint(100, 90)
    QTest.mousePress(widget.view.viewport(), Qt.LeftButton, Qt.NoModifier, start)
    app.sendEvent(
        widget.view.viewport(),
        QMouseEvent(QMouseEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton, Qt.NoModifier),
    )
    moved = [(round(item.x()), round(item.y())) for item in (a, b)]
    assert all(moved[i] != before[i] for i in range(2))
    QTest.mouseRelease(widget.view.viewport(), Qt.LeftButton, Qt.NoModifier, end)
    app.processEvents()
    after = [(seat["x"], seat["y"]) for seat in widget.document["seats"]]
    assert after[:2] == moved
    assert after[2:] == before[2:]
    assert len(widget.history) == history + 1
    widget.undo()
    assert [(s["x"], s["y"]) for s in widget.document["seats"]] == before
    widget.redo()
    assert [(s["x"], s["y"]) for s in widget.document["seats"]] == after
    widget.save()
    saved = editor.read("web-client")["document"]["seats"]
    assert [(s["x"], s["y"]) for s in saved] == after
