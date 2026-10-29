#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# login_screen.py — Pantalla de autenticación con animaciones

from __future__ import annotations

import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QMessageBox, QFrame, QGraphicsDropShadowEffect,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette

from app_version import APP_NAME
from config import Contact
from domain.call_set_policy import OperatingMode
from runtime.secret_manager import password_is_configured
from application.authentication import verify_admin, verify_entry, verify_supercore
from application.login_audit import record_login_event, read_last_login_timestamp

logger = logging.getLogger(__name__)

# Login mode → persistent role granted on success.
#   operator   → CAMERA_OPERATOR (limited: PTZ, names, reconnect)
#   admin      → SYSTEM_ADMIN    (full access)
#   supercore  → SYSTEM_ADMIN    (hidden developer master; full access)
_MODE_ROLE = {
    'operator':  OperatingMode.CAMERA_OPERATOR,
    'admin':     OperatingMode.SYSTEM_ADMIN,
    'supercore': OperatingMode.SYSTEM_ADMIN,
}

# Number of quick taps on the logo that reveals the hidden Supercore login.
_SUPERCORE_TAPS = 5


# Persistent login-audit read/write lives in application/login_audit.py so the
# file path, rotation cap and swallow-on-error contract have a single owner.
# These module-level aliases keep the existing call sites unchanged.
_record_login_event = record_login_event
_read_last_login_timestamp = read_last_login_timestamp


# ═══════════════════════════════════════════════════════════════════════════════
#  PANTALLA DE LOGIN
# ═══════════════════════════════════════════════════════════════════════════════

class LoginScreen(QWidget):
    """Panel de login embebido en MainWindow con bloqueo progresivo."""

    login_successful = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet("QWidget { background-color: #DCDCDC; }")

        # Atributos
        self.attempts = 0
        self.max_attempts = 10
        self.is_locked = False
        self.lockout_timer = None
        self.remaining_seconds = 0

        # Modo de login y rol resultante.
        #   'operator'  (defecto) → CAMERA_OPERATOR
        #   'admin'               → SYSTEM_ADMIN
        #   'supercore' (oculto)  → SYSTEM_ADMIN
        self._mode = 'operator'
        self.authenticated_role = OperatingMode.CAMERA_OPERATOR
        # True solo tras una autenticación manual real (no en sim/bypass).
        self.authenticated = False
        # Contador de toques sobre el logo para revelar el login Supercore.
        self._logo_taps = 0
        self._logo_tap_timer = None

        # Cuenta atrás de auto-entrada como Operador (#login-countdown).
        # El operador no necesita contraseña: la app entra sola tras N segundos,
        # dando una ventana para pulsar "Start now" o cambiar a Admin.
        self._countdown_total = 10
        self._countdown_remaining = self._countdown_total
        self._countdown_timer = None
        # True mientras el login está en modo Operador (entra sin contraseña).
        self._operator_auto = False

        # Horarios de bloqueo: 0, 0, 10s, 10s, 30s, 30s, 60s, 60s, 3600s, 3600s
        self.lockout_schedule = [0, 0, 10, 10, 30, 30, 60, 60, 3600, 3600]

        self._build_ui()
        QTimer.singleShot(0, self._init_login_mode)

    def _check_password_configured(self):
        """Block login with a clear message if no valid password is configured."""
        if not password_is_configured():
            self.password_input.setEnabled(False)
            self.login_btn.setEnabled(False)
            self._set_status(
                '⚠ No password configured — run: python3 setup_password.py',
                'error'
            )

    def _init_login_mode(self):
        """Decide el modo inicial del login al arrancar.

        Si existe el flag legacy de 'restart as admin', se arranca directamente en
        modo Administrador (con contraseña, sin cuenta atrás) para respetar esa
        intención. En cualquier otro caso se entra como **Operador**, con el
        horario semanal (`application/schedule_config.py`) decidiendo si la
        entrada es por cuenta atrás sin contraseña o si pide contraseña de
        operador como fuera de horario.
        """
        try:
            from runtime.path_resolver import RuntimePathResolver
            if RuntimePathResolver().admin_login_flag.exists():
                self._set_mode('admin')
                return
        except Exception:
            logger.debug("login: no se pudo comprobar admin_login.flag")
        self._enter_operator_mode()

    def _enter_operator_mode(self) -> None:
        """(Re)entra en modo Operador aplicando el bypass de horario si procede.

        Dentro del horario configurado (o con `always_bypass`) el operador entra
        por cuenta atrás sin contraseña, igual que antes. Fuera de horario, o si
        el reloj del sistema no es fiable, se pide la contraseña de operador.
        """
        try:
            from application.schedule_config import is_within_schedule, is_clock_plausible
            if not is_clock_plausible():
                self._set_mode('operator', operator_bypass=False)
                self._set_status(
                    'Clock error: system date is invalid. Schedule bypass disabled.',
                    'error',
                )
                return
            self._set_mode('operator', operator_bypass=is_within_schedule())
        except Exception:
            logger.debug("login: schedule check failed — falling back to manual auth")
            self._set_mode('operator', operator_bypass=False)

    def _build_ui(self):
        """Construir interfaz de usuario con card centrada."""
        # ── Outer layout: centra la card en pantalla ───────────────────────────
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()

        # ── Card blanca ────────────────────────────────────────────────────────
        card = QFrame()
        card.setObjectName("LoginCard")
        card.setFixedWidth(580)
        card.setStyleSheet(
            "QFrame#LoginCard { background-color: #FFFFFF; border-radius: 20px; border: none; }"
        )
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 20)
        shadow.setColor(QColor(0, 0, 0, 36))
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(56, 52, 56, 48)
        card_layout.setSpacing(0)

        # ── Logo mark ─────────────────────────────────────────────────────────
        logo_wrap = QHBoxLayout()
        logo_mark = QFrame()
        logo_mark.setObjectName("LogoMark")
        logo_mark.setFixedSize(64, 64)
        logo_mark.setStyleSheet(
            "QFrame#LogoMark {"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            "    stop:0 #4A7A44, stop:1 #1A3318);"
            "  border-radius: 16px; border: none;"
            "}"
        )
        logo_lbl = QLabel('PTZ', logo_mark)
        logo_lbl.setAlignment(Qt.AlignCenter)
        logo_lbl.setGeometry(0, 0, 64, 64)
        logo_lbl.setStyleSheet(
            "QLabel { color: rgba(255,255,255,200); font: 700 18px 'Inter Tight', 'Segoe UI';"
            " background: transparent; border: none; }"
        )
        logo_shadow = QGraphicsDropShadowEffect()
        logo_shadow.setBlurRadius(24)
        logo_shadow.setOffset(0, 4)
        logo_shadow.setColor(QColor(26, 51, 24, 90))
        logo_mark.setGraphicsEffect(logo_shadow)
        # Gesto oculto: varios toques sobre el logo revelan el login Supercore.
        logo_mark.installEventFilter(self)
        self._logo_mark = logo_mark
        logo_wrap.addStretch()
        logo_wrap.addWidget(logo_mark)
        logo_wrap.addStretch()
        card_layout.addLayout(logo_wrap)
        card_layout.addSpacing(20)

        # ── Title ─────────────────────────────────────────────────────────────
        title = QLabel(APP_NAME)
        title.setStyleSheet(
            "QLabel {"
            "  font: 700 36px 'Inter Tight', 'Segoe UI', sans-serif;"
            "  color: #1A3318;"
            "  background: transparent;"
            "  border: none;"
            "  letter-spacing: -1px;"
            "}"
        )
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title)
        card_layout.addSpacing(8)

        # ── Subtitle ──────────────────────────────────────────────────────────
        subtitle = QLabel('Operator Access')
        subtitle.setStyleSheet(
            "QLabel {"
            "  font: 400 19px 'Inter Tight', 'Segoe UI', sans-serif;"
            "  color: #2E5229;"
            "  background: transparent;"
            "  border: none;"
            "}"
        )
        subtitle.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(subtitle)
        self._subtitle = subtitle
        card_layout.addSpacing(44)

        # ── Username (solo visible en login Supercore oculto) ─────────────────
        self.username_label = QLabel('User')
        self.username_label.setStyleSheet(
            "QLabel {"
            "  font: 600 15px 'Inter Tight', 'Segoe UI', sans-serif;"
            "  color: #444444; background: transparent; border: none;"
            "}"
        )
        card_layout.addWidget(self.username_label)
        card_layout.addSpacing(10)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText('Username')
        self.username_input.setFont(QFont('Segoe UI', 18))
        self.username_input.setAlignment(Qt.AlignCenter)
        self.username_input.setStyleSheet("""
            QLineEdit {
                background-color: #FAFAFA;
                border: 2px solid #4A7A44;
                border-radius: 8px;
                padding: 0 20px;
                color: #111111;
            }
            QLineEdit:focus {
                border: 2px solid #2E5229;
                background-color: #FFFFFF;
            }
        """)
        self.username_input.setMinimumHeight(64)
        self.username_input.returnPressed.connect(lambda: self.password_input.setFocus())
        card_layout.addWidget(self.username_input)
        card_layout.addSpacing(12)
        # Oculto por defecto — solo el gesto del logo lo revela.
        self.username_label.setVisible(False)
        self.username_input.setVisible(False)

        # ── Password label ────────────────────────────────────────────────────
        pwd_label = QLabel('Password')
        pwd_label.setStyleSheet(
            "QLabel {"
            "  font: 600 15px 'Inter Tight', 'Segoe UI', sans-serif;"
            "  color: #444444;"
            "  background: transparent;"
            "  border: none;"
            "}"
        )
        card_layout.addWidget(pwd_label)
        card_layout.addSpacing(10)
        self._pwd_label = pwd_label

        # ── Password input ────────────────────────────────────────────────────
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText('Enter password')
        self.password_input.setEchoMode(QLineEdit.Password)
        input_font = QFont('Segoe UI', 18)
        self.password_input.setFont(input_font)
        self.password_input.setAlignment(Qt.AlignCenter)
        self.password_input.setStyleSheet("""
            QLineEdit {
                background-color: #FAFAFA;
                border: 2px solid #4A7A44;
                border-radius: 8px;
                padding: 0 20px;
            }
            QLineEdit:focus {
                border: 2px solid #2E5229;
                background-color: #FFFFFF;
            }
        """)
        # Color de texto y placeholder via paleta (el QSS no define color,
        # así Qt respeta QPalette.PlaceholderText para el hint)
        pal = self.password_input.palette()
        pal.setColor(QPalette.Text, QColor(0x11, 0x11, 0x11))
        pal.setColor(QPalette.PlaceholderText, QColor(160, 160, 160))
        self.password_input.setPalette(pal)
        self.password_input.setMinimumHeight(64)
        self.password_input.returnPressed.connect(self._on_primary_action)
        card_layout.addWidget(self.password_input)
        card_layout.addSpacing(12)

        # ── Status label ──────────────────────────────────────────────────────
        self.status_label = QLabel('')
        self.status_label.setFont(QFont('Inter Tight', 13))
        self.status_label.setStyleSheet(
            "QLabel { color: transparent; background: transparent;"
            " border: none; border-radius: 8px; padding: 10px 14px; }"
        )
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_label.setMinimumHeight(44)
        card_layout.addWidget(self.status_label)
        card_layout.addSpacing(8)

        # ── ACCESS button — gradiente ─────────────────────────────────────────
        self.login_btn = QPushButton('ACCESS')
        self.login_btn.setFont(QFont('Inter Tight', 20, QFont.Bold))
        self.login_btn.setMinimumHeight(80)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #4A7A44, stop:1 #1A3318);
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #3A6A34, stop:1 #0F1F0F);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2E5229, stop:1 #0A1408);
            }
            QPushButton:disabled {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #B0B0B0, stop:1 #888888);
                color: rgba(255,255,255,160);
            }
        """)
        self.login_btn.clicked.connect(self._on_primary_action)
        card_layout.addWidget(self.login_btn)
        card_layout.addSpacing(28)

        # ── Footer: help + exit ───────────────────────────────────────────────
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)

        self.help_btn = QPushButton('? Help')
        self.help_btn.setFont(QFont('Inter Tight', 13))
        self.help_btn.setFixedHeight(28)
        self.help_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #4A7A44;
                border: none;
                padding: 0;
            }
            QPushButton:hover { color: #2E5229; }
            QPushButton:pressed { color: #1A3318; }
        """)
        self.help_btn.clicked.connect(self._show_help)

        # ── Switch user: alterna entre login de Operador y Administrador ──────
        self.switch_btn = QPushButton('Admin login →')
        self.switch_btn.setFont(QFont('Inter Tight', 13))
        self.switch_btn.setFixedHeight(28)
        self.switch_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #4A7A44;
                border: none;
                padding: 0;
            }
            QPushButton:hover { color: #2E5229; }
            QPushButton:pressed { color: #1A3318; }
        """)
        self.switch_btn.clicked.connect(self._on_switch_user)

        self.exit_btn = QPushButton('× Exit')
        self.exit_btn.setFont(QFont('Inter Tight', 13))
        self.exit_btn.setFixedHeight(28)
        self.exit_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: none;
                padding: 0;
            }
            QPushButton:hover { color: #555555; }
            QPushButton:pressed { color: #222222; }
        """)
        self.exit_btn.clicked.connect(self.exit_requested)

        footer_row.addWidget(self.help_btn)
        footer_row.addStretch()
        footer_row.addWidget(self.switch_btn)
        footer_row.addStretch()
        footer_row.addWidget(self.exit_btn)
        card_layout.addLayout(footer_row)

        last_login_text = _read_last_login_timestamp()
        if last_login_text:
            last_login_lbl = QLabel(last_login_text)
            last_login_lbl.setFont(QFont('Inter Tight', 11))
            last_login_lbl.setStyleSheet(
                "QLabel { color: #888888; background: transparent; border: none; }"
            )
            last_login_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            card_layout.addSpacing(8)
            card_layout.addWidget(last_login_lbl)

        outer.addWidget(card, alignment=Qt.AlignVCenter)
        outer.addStretch()

        # Auto-focus en campo de contraseña
        self.password_input.setFocus()

    def _show_help(self):
        QMessageBox.information(self, 'For Technical Assistance', Contact, QMessageBox.Ok)

    # ── Cambio de modo (Operador / Administrador / Supercore oculto) ───────────

    def _set_mode(self, mode: str, *, operator_bypass: bool = True) -> None:
        """Cambia el modo de login y actualiza la UI (subtítulo, campos, botón).

        - operator  → entra por cuenta atrás sin contraseña cuando
                      ``operator_bypass`` es True (dentro del horario configurado
                      en Settings → Access); si es False (fuera de horario, o
                      reloj no fiable), pide la contraseña de operador como en
                      modo Admin.
        - admin     → contraseña de administrador.
        - supercore → usuario + contraseña maestra (oculto).
        """
        self._mode = mode
        self.attempts = 0
        self.username_input.clear()
        self.password_input.clear()
        self._set_status('', 'hidden')
        self._cancel_countdown()

        is_operator = mode == 'operator'
        is_supercore = mode == 'supercore'
        # El operador entra sin contraseña solo si el horario lo permite.
        self._operator_auto = is_operator and operator_bypass

        # Campos visibles según el modo. El operador en bypass no teclea contraseña.
        self.username_label.setVisible(is_supercore)
        self.username_input.setVisible(is_supercore)
        self._pwd_label.setVisible(not self._operator_auto)
        self.password_input.setVisible(not self._operator_auto)

        if mode == 'operator':
            self._subtitle.setText('Operator Access')
            self.switch_btn.setText('Admin login →')
            self.switch_btn.setVisible(True)
        elif mode == 'admin':
            self._subtitle.setText('Administrator Access')
            self.switch_btn.setText('← Operator login')
            self.switch_btn.setVisible(True)
        else:  # supercore
            self._subtitle.setText('Developer Access')
            self.switch_btn.setText('← Operator login')
            self.switch_btn.setVisible(True)

        if self._operator_auto:
            # Auto-entrada con cuenta atrás: sin contraseña (dentro de horario).
            self.is_locked = False
            self.login_btn.setEnabled(True)
            self._start_operator_countdown()
            self.login_btn.setFocus()
        elif is_supercore:
            # Credencial maestra independiente de password.enc: reactivar el
            # formulario incluso si el cliente nunca configuró contraseña.
            self.is_locked = False
            self.password_input.setEnabled(True)
            self.login_btn.setEnabled(True)
            self.login_btn.setText('ACCESS')
            self.username_input.setFocus()
        else:  # admin, u operador fuera de horario (pide contraseña de operador)
            self.login_btn.setText('ACCESS')
            self._check_password_configured()
            self.password_input.setFocus()

    # ── Cuenta atrás de auto-entrada como Operador ─────────────────────────────

    def _start_operator_countdown(self) -> None:
        """Arranca la cuenta atrás que entra como Operador al llegar a cero."""
        self._countdown_remaining = self._countdown_total
        if self._countdown_timer is None:
            self._countdown_timer = QTimer(self)
            self._countdown_timer.timeout.connect(self._tick_countdown)
        self._update_start_button()
        self._countdown_timer.start(1000)

    def _cancel_countdown(self) -> None:
        """Detiene la cuenta atrás (al cambiar de modo o entrar manualmente)."""
        if self._countdown_timer is not None:
            self._countdown_timer.stop()

    def _tick_countdown(self) -> None:
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._enter_operator()
            return
        self._update_start_button()

    def _update_start_button(self) -> None:
        """Refresca el texto del botón con los segundos restantes."""
        self.login_btn.setText(f'Start now  ·  {self._countdown_remaining}s')

    def _enter_operator(self) -> None:
        """Entra como Operador inmediatamente (botón 'Start now' o fin de cuenta)."""
        self._cancel_countdown()
        self._mode = 'operator'
        self._on_login_success()

    def _on_primary_action(self) -> None:
        """Acción del botón principal / Enter según el modo activo.

        Solo el operador en auto-entrada (schedule bypass) entra sin contraseña;
        en cualquier otro caso se verifica la credencial introducida.
        """
        if self._mode == 'operator' and getattr(self, '_operator_auto', False):
            self._enter_operator()
        else:
            self._verify_password()

    def _on_switch_user(self) -> None:
        """Operador ⇄ Administrador. Desde Supercore vuelve a Operador."""
        if self._mode == 'operator':
            self._set_mode('admin')
        else:
            self._enter_operator_mode()

    def eventFilter(self, obj, event):
        """Detecta toques repetidos sobre el logo para revelar Supercore."""
        from PyQt5.QtCore import QEvent
        if obj is getattr(self, '_logo_mark', None) and event.type() == QEvent.MouseButtonPress:
            self._register_logo_tap()
            return False
        return super().eventFilter(obj, event)

    def _register_logo_tap(self) -> None:
        """Cuenta toques sobre el logo; al alcanzar el umbral abre Supercore."""
        if self._mode == 'supercore':
            return
        self._logo_taps += 1
        if self._logo_tap_timer is None:
            self._logo_tap_timer = QTimer(self)
            self._logo_tap_timer.setSingleShot(True)
            self._logo_tap_timer.timeout.connect(self._reset_logo_taps)
        self._logo_tap_timer.start(2000)  # ventana de 2s para completar la secuencia
        if self._logo_taps >= _SUPERCORE_TAPS:
            self._reset_logo_taps()
            self._set_mode('supercore')

    def _reset_logo_taps(self) -> None:
        self._logo_taps = 0
        if self._logo_tap_timer is not None:
            self._logo_tap_timer.stop()

    def _verify_password(self):
        """Verificar credenciales según el modo activo (operador/admin/supercore)."""
        # No hacer nada si está bloqueado
        if self.is_locked:
            return

        pwd = self.password_input.text()

        # Validar que no esté vacía
        if not pwd:
            self._set_status('✗ Password required', 'warning')
            return

        # Supercore: credencial maestra hasheada en el binario (no depende del
        # password.enc del cliente). Se valida usuario + contraseña.
        if self._mode == 'supercore':
            user = self.username_input.text()
            if not user:
                self._set_status('✗ Username required', 'warning')
                return
            if verify_supercore(user, pwd):
                self._on_login_success()
            else:
                self._on_login_failure()
            return

        # Administrador: requiere password.enc configurado (el Operador entra por
        # cuenta atrás sin contraseña y no llega aquí).
        # Guard against the secret disappearing between app start and this
        # attempt (e.g. password.enc deleted): disable the form rather than
        # counting it as a wrong attempt.
        if not password_is_configured():
            self.password_input.setEnabled(False)
            self.login_btn.setEnabled(False)
            self._set_status(
                '⚠ No password configured — run: python3 setup_password.py',
                'error'
            )
            return

        # Constant-time comparison via the central auth service.
        verify = verify_admin if self._mode == 'admin' else verify_entry
        if verify(pwd):
            self._on_login_success()
        else:
            self._on_login_failure()

    # ── Status helper ──────────────────────────────────────────────────────────

    def _set_status(self, text: str, variant: str):
        """Actualiza status_label con el variant visual correcto."""
        styles = {
            'warning': (
                "QLabel { color: #B84F00; background: #FFF3E6;"
                " border: 1px solid rgba(184,79,0,0.30);"
                " border-radius: 8px; padding: 10px 14px; }"
            ),
            'error': (
                "QLabel { color: #C0141F; background: #FCECEA;"
                " border: 1px solid rgba(192,20,31,0.30);"
                " border-radius: 8px; padding: 10px 14px; }"
            ),
            'success': (
                "QLabel { color: #1B7F3E; background: #EAF6EE;"
                " border: 1px solid rgba(27,127,62,0.30);"
                " border-radius: 8px; padding: 10px 14px; }"
            ),
            'hidden': (
                "QLabel { color: transparent; background: transparent;"
                " border: none; border-radius: 8px; padding: 10px 14px; }"
            ),
        }
        self.status_label.setText(text)
        self.status_label.setStyleSheet(styles.get(variant, styles['hidden']))

    # ── Login logic ────────────────────────────────────────────────────────────

    def _on_login_success(self):
        """Manejar login exitoso."""
        # El rol concedido depende del modo con el que se autenticó.
        self.authenticated_role = _MODE_ROLE.get(
            self._mode, OperatingMode.CAMERA_OPERATOR
        )
        self.authenticated = True
        _record_login_event(success=True, attempts=self.attempts)
        self.password_input.clear()
        self.username_input.clear()
        self._set_status('✓ Access granted', 'success')
        self.login_btn.setEnabled(False)
        self.password_input.setEnabled(False)

        # Animar fade out
        self._animate_fade_out()

    def _animate_fade_out(self):
        """
        Transición login → splash: emite la señal directamente.
        (Como widget embebido, la ocultación la gestiona MainWindow.)
        """
        self.login_successful.emit()

    def _on_login_failure(self):
        """Manejar login fallido con bloqueo progresivo."""
        self.attempts += 1
        _record_login_event(success=False, attempts=self.attempts)
        self.password_input.clear()

        # Obtener duración de bloqueo según número de intentos
        lockout_seconds = self.lockout_schedule[min(self.attempts - 1, 9)]

        if lockout_seconds > 0:
            # Aplicar bloqueo temporal
            self.is_locked = True
            self.password_input.setEnabled(False)
            self.login_btn.setEnabled(False)

            self._set_status(
                f'⏱ Locked for {lockout_seconds}s ({self.attempts} attempts)',
                'error'
            )
            # Iniciar countdown
            self._start_lockout_timer(lockout_seconds)
        else:
            # Permitir reintento inmediato
            remaining = 10 - self.attempts
            self._set_status(
                f'✗ Wrong password ({remaining} attempts left)',
                'warning'
            )
            self.password_input.setFocus()

    def _start_lockout_timer(self, seconds: int):
        """Countdown de bloqueo temporal."""
        self.lockout_timer = QTimer(self)
        self.remaining_seconds = seconds

        def update_countdown():
            """Decrementar contador cada segundo."""
            self.remaining_seconds -= 1

            if self.remaining_seconds > 0:
                self._set_status(f'⏱ Locked for {self.remaining_seconds}s', 'error')
            else:
                # Desbloquear cuando termine
                self.is_locked = False
                self.password_input.setEnabled(True)
                self.login_btn.setEnabled(True)
                self._set_status('✓ Unlock complete — retry', 'success')
                self.password_input.setFocus()
                # Detener timer
                self.lockout_timer.stop()

        # Ejecutar actualización cada segundo
        self.lockout_timer.timeout.connect(update_countdown)
        self.lockout_timer.start(1000)
