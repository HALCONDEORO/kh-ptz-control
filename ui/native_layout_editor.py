"""Native Qt sandbox editor over the same transaction service as the web UI.

No cameras, production data or network setup. Embeddable widget; explicit test
launcher owns the shared service, OS workspace lock and optional HTTP server.
"""

from __future__ import annotations

from copy import deepcopy
import secrets
import uuid
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QPen
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from application.web_layout_editor import EditorError
from ui.styles import BRAND_DARK, FIELD_BG, primary_button_qss, secondary_button_qss


class SeatItem(QGraphicsRectItem):
    def __init__(self, seat, changed):
        super().__init__(0, 0, 40, 40)
        self.seat = seat
        self.changed = changed
        self.setBrush(QBrush(QColor("#eef1e9")))
        self.setPen(QPen(QColor("#68765f")))
        self.setPos(seat["x"], seat["y"])
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable, not seat["locked"])
        self.text = None

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.changed(self, round(self.x()), round(self.y()))


class NativeLayoutEditor(QDialog):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.session = "native:" + secrets.token_urlsafe(24)
        self.generation = None
        self._finalized = False
        self._lease_holder = {"generation": None}
        holder, session = self._lease_holder, self.session

        def release_destroyed(*_):
            try:
                editor.release(session, holder["generation"])
            except (EditorError, OSError, ValueError):
                pass

        self.destroyed.connect(release_destroyed)
        self.document = None
        self.revision = None
        self.dirty = False
        self.history = []
        self.future = []
        self.setWindowTitle("KH PTZ Control | Native layout test | No cameras")
        self.resize(1280, 900)
        self.setStyleSheet(
            f"QDialog {{ background: #f8f9fa; }} QLabel {{ color: {BRAND_DARK}; font-size: 13px; }} QLineEdit {{ padding: 8px; background: {FIELD_BG}; border: 1px solid #dce2d8; border-radius: 6px; }}"
        )
        root = QVBoxLayout(self)
        title = QLabel("KH PTZ CONTROL  |  NATIVE EDITOR TEST  |  SIMULATION, NO CAMERAS")
        root.addWidget(title)
        root.addWidget(
            QLabel("Shared sandbox master. New seats have no camera memory. No real hall changes.")
        )
        bar = QHBoxLayout()
        self.buttons = {}
        for key, label, action in [
            ("take", "Start editing", self.take),
            ("block", "+ Block 4-6-4", self.block),
            ("add", "+ Seat", self.add),
            ("remove", "Delete selection", self.remove),
            ("undo", "Undo", self.undo),
            ("redo", "Redo", self.redo),
            ("reload", "Reload", self.load),
            ("save", "Save layout", self.save),
            ("leave", "Leave editing", self.leave),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, fn=action: self.run(fn))
            button.setMinimumHeight(40)
            button.setStyleSheet(
                primary_button_qss() if key in ("save", "take") else secondary_button_qss()
            )
            self.buttons[key] = button
            bar.addWidget(button)
        root.addLayout(bar)
        namebar = QHBoxLayout()
        namebar.addWidget(QLabel("Hall name"))
        self.name = QLineEdit()
        self.name.editingFinished.connect(lambda: self.run(self.rename_room))
        namebar.addWidget(self.name)
        root.addLayout(namebar)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        root.addWidget(self.view)
        self.scene.selectionChanged.connect(self.controls)
        self.info = QLabel("No seat selected")
        root.addWidget(self.info)
        self.label = QLineEdit()
        self.label.setPlaceholderText("Selected seat label")
        self.label.editingFinished.connect(lambda: self.run(self.relabel))
        root.addWidget(self.label)
        self.locked = QCheckBox("Lock selected seat position")
        self.locked.clicked.connect(lambda: self.run(self.toggle_lock))
        root.addWidget(self.locked)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.setInterval(25000)
        self.timer.timeout.connect(lambda: self.run(self.renew))
        self.timer.start()
        self.poll = QTimer(self)
        self.poll.setInterval(5000)
        self.poll.timeout.connect(lambda: self.run(self.refresh))
        self.poll.start()
        self.run(self.load)

    def run(self, action):
        try:
            action()
        except EditorError as exc:
            if exc.code == "lease_required":
                self.generation = None
                self.render()
            self.status.setText(
                "Request failed: "
                + exc.code
                + ". Draft kept; master unchanged unless save was confirmed."
            )
        except (OSError, ValueError):
            self.status.setText("Request failed. Check the master before retrying. Draft kept.")
        self.controls()

    def controls(self):
        editing = self.generation is not None
        for key, button in self.buttons.items():
            button.setEnabled(
                (not editing) if key == "take" else True if key == "reload" else editing
            )
        self.name.setEnabled(editing)
        selected = self.scene.selectedItems()
        self.label.setEnabled(editing and len(selected) == 1)
        self.locked.setEnabled(editing and len(selected) == 1)
        self.locked.setChecked(len(selected) == 1 and selected[0].seat["locked"])
        self.buttons["remove"].setEnabled(editing and bool(selected))
        self.buttons["undo"].setEnabled(editing and bool(self.history))
        self.buttons["redo"].setEnabled(editing and bool(self.future))
        if len(selected) == 1:
            seat = selected[0].seat
            self.info.setText("ID: " + seat["id"] + " | Memory: " + str(seat["preset"]))
            if not self.label.hasFocus():
                self.label.setText(seat["label"])
        else:
            self.info.setText("No seat selected")
            self.label.clear()

    def checkpoint(self):
        self.history.append(deepcopy(self.document))
        self.history = self.history[-100:]
        self.future.clear()
        self.dirty = True

    def discard_ok(self):
        return (
            not self.dirty
            or QMessageBox.question(
                self,
                "Unsaved changes",
                "Discard unsaved changes?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    def load(self):
        if not self.discard_ok():
            return
        result = self.editor.read(self.session)
        self.document, self.revision = result["document"], result["revision"]
        if result["lease"] != "mine":
            self.generation = None
        self.dirty = False
        self.history.clear()
        self.future.clear()
        self.render()
        self.status.setText("Master loaded | version " + self.revision[:8])

    def render(self):
        self.scene.clear()
        if not self.document:
            return
        self.name.setText(self.document["room_name"])
        self.scene.setSceneRect(0, 0, self.document["screen_width"], self.document["screen_height"])
        for seat in self.document["seats"]:
            if not seat["visible"]:
                continue
            item = SeatItem(seat, self.move_seat)
            item.setFlag(QGraphicsItem.ItemIsMovable, bool(self.generation) and not seat["locked"])
            self.scene.addItem(item)
            text = self.scene.addText(seat["label"])
            text.setParentItem(item)
            text.setAcceptedMouseButtons(Qt.NoButton)
            text.setPos(5, 7)
        self.fit_readable()
        self.controls()

    def fit_readable(self):
        self.view.resetTransform()
        area = self.scene.sceneRect()
        if area.width() and area.height():
            scale = max(
                0.9,
                min(
                    self.view.viewport().width() / area.width(),
                    self.view.viewport().height() / area.height(),
                ),
            )
            self.view.scale(scale, scale)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_readable()

    def take(self):
        if self._finalized:
            return
        if not self.dirty:
            self.load()
        lease = self.editor.acquire(self.session)
        self.generation = lease["generation"]
        self._lease_holder["generation"] = self.generation
        self.render()
        self.status.setText("Your editing turn. Save layout to change the shared master.")

    def renew(self):
        if self.generation:
            self.editor.renew(self.session, self.generation)

    def refresh(self):
        if self.generation or self.dirty:
            return
        result = self.editor.read(self.session)
        if result["revision"] != self.revision:
            self.document, self.revision = result["document"], result["revision"]
            self.history.clear()
            self.future.clear()
            self.render()
            self.status.setText("Updated from shared master | version " + self.revision[:8])

    def save(self):
        if not self.generation:
            return
        result = self.editor.save(self.session, self.revision, self.document, self.generation)
        self.document, self.revision = result["document"], result["revision"]
        self.dirty = False
        self.render()
        self.status.setText(
            "Save confirmed | version " + self.revision[:8] + " | previous copy preserved"
        )

    def leave(self):
        if not self.discard_ok():
            return False
        self.editor.release(self.session, self.generation)
        self.generation = None
        self.dirty = False
        self.load()
        return True

    def new_seat(self, x, y, label, row=None, column=None):
        return dict(
            id=str(uuid.uuid4()),
            label=str(label),
            preset=0,
            camera_role="comments",
            x=x,
            y=y,
            row=row,
            column=column,
            type="delegate",
            visible=True,
            locked=False,
            calibrated=False,
        )

    def add(self):
        if not self.generation:
            return
        if len(self.document["seats"]) >= 1000:
            return
        self.checkpoint()
        self.document["seats"].append(self.new_seat(60, 80, len(self.document["seats"]) + 1))
        self.render()

    def block(self):
        if not self.generation:
            return
        rows, accepted = QInputDialog.getInt(
            self, "Create a block", "Rows (groups 4-6-4)", 6, 1, 20
        )
        if not accepted:
            return
        self.create_block(rows)

    def create_block(self, rows):
        if not self.generation or type(rows) is not int or not 1 <= rows <= 20:
            return
        width, height = self.document["screen_width"], self.document["screen_height"]
        if (
            60 + 13 * 55 + 80 + 40 > width
            or 100 + (rows - 1) * 70 + 40 > height
            or len(self.document["seats"]) + rows * 14 > 1000
        ):
            raise ValueError("Block does not fit")
        self.checkpoint()
        number = len(self.document["seats"]) + 1
        for row in range(rows):
            x, column = 60, 1
            for group in (4, 6, 4):
                for _ in range(group):
                    self.document["seats"].append(
                        self.new_seat(x, 100 + row * 70, number, row + 1, column)
                    )
                    x += 55
                    column += 1
                    number += 1
                x += 40
        self.render()

    def remove(self):
        if not self.generation:
            return
        ids = {item.seat["id"] for item in self.scene.selectedItems() if not item.seat["locked"]}
        if not ids:
            return
        self.checkpoint()
        self.document["seats"] = [seat for seat in self.document["seats"] if seat["id"] not in ids]
        self.render()

    def move_seat(self, item, x, y):
        if not self.generation or item.seat["locked"]:
            self.render()
            return
        # Qt moves every movable selected item during one drag. Commit the
        # complete gesture before rebuilding the scene, with one undo entry.
        candidates = {
            selected for selected in self.scene.selectedItems() if isinstance(selected, SeatItem)
        }
        candidates.add(item)
        changes = []
        for selected in candidates:
            if selected.seat["locked"]:
                continue
            sx, sy = (x, y) if selected is item else (round(selected.x()), round(selected.y()))
            sx = max(0, min(self.document["screen_width"] - 40, sx))
            sy = max(0, min(self.document["screen_height"] - 40, sy))
            if (sx, sy) != (selected.seat["x"], selected.seat["y"]):
                changes.append((selected.seat, sx, sy))
        if changes:
            self.checkpoint()
            for seat, sx, sy in changes:
                seat.update(x=sx, y=sy)
            QTimer.singleShot(0, self.render)

    def toggle_lock(self):
        selected = self.scene.selectedItems()
        if not self.generation or len(selected) != 1:
            return
        self.checkpoint()
        selected[0].seat["locked"] = self.locked.isChecked()
        self.render()

    def rename_room(self):
        value = self.name.text().strip()
        if self.generation and value and value != self.document["room_name"]:
            self.checkpoint()
            self.document["room_name"] = value

    def relabel(self):
        selected = self.scene.selectedItems()
        value = self.label.text().strip()
        if self.generation and len(selected) == 1 and value and value != selected[0].seat["label"]:
            self.checkpoint()
            selected[0].seat["label"] = value
            self.render()

    def undo(self):
        if self.generation and self.history:
            self.future.append(deepcopy(self.document))
            self.document = self.history.pop()
            self.dirty = True
            self.render()

    def redo(self):
        if self.generation and self.future:
            self.history.append(deepcopy(self.document))
            self.document = self.future.pop()
            self.dirty = True
            self.render()

    def showEvent(self, event):
        if self._finalized:
            self._finalized = False
            self.timer.start()
            self.poll.start()
            self.run(self.load)
        super().showEvent(event)

    def _finalize(self):
        if self._finalized:
            return True
        if not self.discard_ok():
            return False
        try:
            self.editor.release(self.session, self.generation)
        except (EditorError, OSError, ValueError):
            # No renewal survives a failed release. Server-side lease expires.
            self.status.setText("Could not release editing turn. It will expire automatically.")
        finally:
            self.generation = None
            self._lease_holder["generation"] = None
            self.timer.stop()
            self.poll.stop()
            self.dirty = False
            self._finalized = True
        return True

    def done(self, result):
        if self._finalize():
            super().done(result)

    def accept(self):
        self.done(QDialog.Accepted)

    def reject(self):
        self.done(QDialog.Rejected)

    def closeEvent(self, event):
        if self._finalize():
            event.accept()
        else:
            event.ignore()
