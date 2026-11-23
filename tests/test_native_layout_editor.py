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


def test_native_visual(native):
    widget, _, app = native
    widget.take()
    widget.create_block(6)
    widget.save()
    widget.show()
    app.processEvents()
    assert widget.grab().save("/downloads/kh-native-layout-editor.png")


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
