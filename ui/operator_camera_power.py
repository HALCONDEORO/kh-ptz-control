"""Operator session power action. Uses the existing standby/start session path."""
from PyQt5.QtCore import QEvent, QRectF, Qt, QVariantAnimation
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class PastelPowerButton(QPushButton):
    """Paint-only state transition, independent of camera command timing."""
    def __init__(self, parent):
        super().__init__(parent)
        self._active = None
        self._fill = QColor('#d8eee2')
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(300)
        self._animation.valueChanged.connect(self._set_fill)
        from ui.styles import apply_shadow
        apply_shadow(self, blur=16, offset=(0, 4), color=(45, 58, 64, 55))

    def _set_fill(self, value):
        self._fill = value
        self.update()

    def set_active(self, active):
        if active == self._active:
            return
        initial = self._active is None
        self._active = active
        target = QColor('#f4dce4' if active else '#d8eee2')
        self._animation.stop()
        if initial:
            self._set_fill(target)
        else:
            self._animation.setStartValue(self._fill)
            self._animation.setEndValue(target)
            self._animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._fill if self.isEnabled() else QColor('#e7e7e7'))
        rect = QRectF(self.rect()).adjusted(3, 3, -3, -5)
        painter.drawRoundedRect(rect, 24, 24)
        ink = QColor('#a52550' if self._active else '#087354')
        if not self.isEnabled():
            ink = QColor('#777777')
        if self.isDown():
            painter.fillPath(self._pill_path(rect), QColor(0, 0, 0, 15))
        cy = rect.center().y()
        painter.setBrush(QColor('white'))
        painter.drawEllipse(QRectF(12, cy - 14, 28, 28))
        painter.setBrush(ink)
        if self._active:
            painter.drawRoundedRect(QRectF(21, cy - 7, 4, 14), 1, 1)
            painter.drawRoundedRect(QRectF(28, cy - 7, 4, 14), 1, 1)
        else:
            path = QPainterPath()
            path.moveTo(22, cy - 8)
            path.lineTo(34, cy)
            path.lineTo(22, cy + 8)
            path.closeSubpath()
            painter.drawPath(path)
        # Two camera bodies plus lenses, independent of font glyph coverage.
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(ink, 1.8))
        for x, y in ((54, cy - 11), (70, cy - 2)):
            painter.drawRoundedRect(QRectF(x, y, 23, 15), 3, 3)
            lens = QPainterPath()
            lens.moveTo(x + 23, y + 5)
            lens.lineTo(x + 30, y + 1)
            lens.lineTo(x + 30, y + 14)
            lens.lineTo(x + 23, y + 10)
            lens.closeSubpath()
            painter.drawPath(lens)
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(ink)
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 22, 22)

    @staticmethod
    def _pill_path(rect):
        path = QPainterPath()
        path.addRoundedRect(rect, 24, 24)
        return path


class OperatorCameraPower(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._standby_requested = False
        self.setGeometry(10, 10, 132, 76)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.button = PastelPowerButton(self)
        self.button.setFixedSize(118, 48)
        self.button.setAutoDefault(False)
        self.button.setDefault(False)
        self.button.clicked.connect(self._request)
        layout.addWidget(self.button)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setStyleSheet('color: #51484a; font-size: 12px;')
        layout.addWidget(self.status)
        window.BtnSession.installEventFilter(self)
        self.refresh()
        self.show()
        self.raise_()

    def eventFilter(self, watched, event):
        if watched is self.window.BtnSession and event.type() == QEvent.EnabledChange:
            self.refresh()
        return super().eventFilter(watched, event)

    def refresh(self):
        active = bool(self.window.session_active)
        ready = self.window.BtnSession.isEnabled()
        closing = bool(getattr(self.window, '_shutting_down', False))
        self.button.setEnabled(ready and not closing)
        self.button.setText('Power off cameras' if active else 'Power on cameras')
        self.button.setAccessibleName(self.button.text())
        self.button.setToolTip(self.button.text() + '\nStandby only. Does not cut electrical power.')
        self.button.set_active(active)
        if active:
            self._standby_requested = False
        self.status.setText('i')
        self.status.setAccessibleName('Camera standby information')
        feedback = ('Starting cameras.' if active and not ready else
                    'Standby requested. Check both cameras.' if self._standby_requested else
                    'Camera session active.' if active else 'Session inactive.')
        self.status.setToolTip(feedback + '\nStandby only. Does not cut electrical power.')


    def _request(self):
        if not self.button.isEnabled() or getattr(self.window, '_shutting_down', False):
            return
        if getattr(self, '_dialog', None) is not None:
            return
        from ui.camera_power_dialog import build_camera_power_dialog
        active = bool(self.window.session_active)
        generation = self.window._session._session_generation
        box, yes = build_camera_power_dialog(self.window, power_on=not active)
        self._dialog = box

        def finished(_result):
            self._dialog = None
            if (box.clickedButton() is yes
                    and not getattr(self.window, '_shutting_down', False)
                    and bool(self.window.session_active) == active
                    and self.window._session._session_generation == generation):
                if active:
                    self.window._session.shutdown('manual')
                    self._standby_requested = True
                else:
                    self.window._session.ToggleSession()
            self.refresh()
            box.deleteLater()

        box.finished.connect(finished)
        box.open()
