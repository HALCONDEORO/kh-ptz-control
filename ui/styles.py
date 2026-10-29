#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Centralised design tokens and parser-safe QSS/effect helpers.

Raspberry Pi OS Bullseye ships Qt 5.15. Its stylesheet parser rejects several
CSS-like ``font`` shorthand forms, especially a shorthand followed by multiple
fallback families. Keep font size, weight and family as separate properties so
the same styles work on the Pi and on newer desktop Qt builds.
"""
from __future__ import annotations

BRAND_DARK = '#1A3318'
BRAND_MID = '#2E5229'
BRAND_LIGHT = '#4A7A44'
SUCCESS = '#1B7F3E'
SUCCESS_BG = '#EAF6EE'
SUCCESS_BD = 'rgba(27, 127, 62, 0.30)'
WARNING = '#B84F00'
WARNING_BG = '#FFF3E6'
WARNING_BD = 'rgba(184, 79, 0, 0.30)'
ERROR = '#C0141F'
ERROR_BG = '#FCECEA'
ERROR_BD = 'rgba(192, 20, 31, 0.40)'
CARD_BD = '#ECEEEC'
FIELD_BG = '#F8F9F6'
FIELD_BD = '#E6E8E2'
MUTED = '#666666'
SECONDARY = '#444444'


def _font_qss(font_px: int, *, weight: str = "normal", family: str = "Inter Tight") -> str:
    """Longhand font declarations that every Qt build we support can parse.

    Weights are named (``normal`` / ``bold``), never numeric: Qt 5.15 on
    Bullseye is unreliable with ``font-weight: 600`` and rejects the sheet it
    appears in, which is what left the wizard unstyled on the device (#886).
    """
    return (
        f"font-size: {font_px}px; font-weight: {weight}; "
        f"font-family: '{family}';"
    )


def primary_button_qss(
    radius: int = 10,
    font_px: int = 13,
    grad_start: str = BRAND_MID,
    grad_end: str = BRAND_DARK,
    pressed: str = BRAND_DARK,
) -> str:
    """Filled gradient call-to-action button."""
    return (
        "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
        f" stop:0 {grad_start}, stop:1 {grad_end});"
        f" border: none; border-radius: {radius}px; {_font_qss(font_px, weight='bold')}"
        " color: white; }"
        f"QPushButton:pressed {{ background: {pressed}; }}"
    )


def secondary_button_qss(radius: int = 10, font_px: int = 13) -> str:
    """Outlined white secondary button."""
    return (
        "QPushButton { background: white; border: 1px solid #DCDEDB;"
        f" border-radius: {radius}px; {_font_qss(font_px, weight='bold')}"
        f" color: {SECONDARY}; }}"
        "QPushButton:hover { background: #F6F7F5; border-color: #C8CAC6;"
        f" color: {BRAND_DARK}; }}"
        "QPushButton:pressed { background: #EBEBEB; }"
    )


def close_button_qss(radius: int = 7, font_px: int = 13) -> str:
    """Square close button."""
    return (
        f"QPushButton {{ background: {ERROR_BG}; border: 1px solid {ERROR_BD};"
        f" border-radius: {radius}px; font-size: {font_px}px; font-weight: bold;"
        f" color: {ERROR}; }}"
        f"QPushButton:hover {{ background: {ERROR}; border-color: {ERROR}; color: white; }}"
        "QPushButton:pressed { background: #8E0F18; }"
    )


def icon_button_qss(radius: int = 8) -> str:
    return (
        "QPushButton { background: white; border: 1px solid #DCDEDB;"
        f" border-radius: {radius}px; }}"
        "QPushButton:hover { background: #F6F7F5; border-color: #C8CAC6; }"
        "QPushButton:pressed { background: #EBEBEB; }"
    )


def input_field_qss() -> str:
    return (
        f"QLineEdit {{ border: 1px solid {FIELD_BD}; border-radius: 8px;"
        " padding: 8px 12px; font-size: 14px; font-family: 'Consolas';"
        f" background: {FIELD_BG}; color: #111; }}"
        f"QLineEdit:focus {{ border: 2px solid {BRAND_MID}; }}"
    )


def error_label_qss(font_px: int = 11) -> str:
    """Inline validation/error text."""
    return f"color: {ERROR}; {_font_qss(font_px)}"


def success_label_qss(font_px: int = 13) -> str:
    """Inline confirmation text (used by the Raspberry Pi wizard pages)."""
    return f"color: {SUCCESS}; {_font_qss(font_px, weight='bold')}"


def setup_wizard_qss() -> str:
    """Branded look for the touchscreen setup wizard.

    Applied once on the ``QWizard`` so it cascades to every page: soft card-like
    group boxes, branded inputs with a focus ring, comfortable touch targets and
    the brand button treatment. This keeps the wizard consistent with the rest of
    the product instead of the raw native theme, without styling each page.

    Uses longhand ``font-size`` / ``font-weight`` / ``font-family`` declarations
    rather than the ``font:`` shorthand. The Qt 5.15 build shipped on Raspberry
    Pi OS Bullseye rejects the whole sheet with "Could not parse stylesheet of
    object SetupWizard" when it meets a shorthand carrying a numeric weight, so
    the wizard rendered unstyled on the real device (#886). The longhand form is
    parsed consistently across the Qt versions we support.
    """
    return (
        # ── Page surface + base font ──
        "QWizard, QWizardPage {"
        " background: white; font-family: 'Inter Tight', 'Segoe UI';"
        " color: #1A1A1A; }"
        "QWizardPage { font-size: 14px; }"
        # ── Group boxes as soft cards ──
        f"QGroupBox {{ border: 1px solid {CARD_BD}; border-radius: 10px;"
        " margin-top: 14px; padding: 14px 12px 10px 12px;"
        f" {_font_qss(13, weight='bold')} color: {BRAND_DARK}; }}"
        "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        f"QLineEdit {{ border: 1px solid {FIELD_BD}; border-radius: 8px;"
        # No font-family: 'Segoe UI' does not exist on Raspberry Pi OS, so the
        # field would silently fall back anyway. Inheriting from QWizard keeps
        # one font decision in one place.
        " padding: 8px 12px; font-size: 14px;"
        f" background: {FIELD_BG}; color: #111; }}"
        f"QLineEdit:focus {{ border: 2px solid {BRAND_MID}; }}"
        f"QComboBox {{ border: 1px solid {FIELD_BD}; border-radius: 8px;"
        f" padding: 6px 12px; background: {FIELD_BG}; color: #111;"
        # NOTE: plain (non-f) string — a single brace, not the doubled form.
        # A stray "}" here closed a block that was never opened and made Qt
        # reject the entire sheet: "Could not parse stylesheet of object
        # SetupWizard" (#886).
        " font-size: 14px; min-height: 24px; }"
        f"QComboBox:focus {{ border: 2px solid {BRAND_MID}; }}"
        # ── Checkbox (comfortable touch target) ──
        "QCheckBox { font-size: 14px; spacing: 8px; }"
        "QCheckBox::indicator { width: 20px; height: 20px; }"
        "QPushButton { background: white; border: 1px solid #DCDEDB;"
        " border-radius: 9px; padding: 7px 16px; min-width: 90px; min-height: 34px;"
        f" {_font_qss(13, weight='bold')} color: {SECONDARY}; }}"
        "QPushButton:hover { background: #F6F7F5; border-color: #C8CAC6;"
        f" color: {BRAND_DARK}; }}"
        "QPushButton:pressed { background: #EBEBEB; }"
        "QPushButton:disabled { color: #AAB2AA; border-color: #EEEEEE; }"
        "QPushButton:default { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
        f" stop:0 {BRAND_MID}, stop:1 {BRAND_DARK});"
        " border: none; color: white; }"
        f"QPushButton:default:pressed {{ background: {BRAND_DARK}; }}"
    )


def apply_stylesheet_safely(widget, qss: str) -> bool:
    """Apply *qss* to *widget*, falling back to native styling if Qt rejects it.

    Qt reports an unparseable stylesheet as a warning and then renders the
    widget with a partially-applied sheet, which looks broken rather than
    plain. On an appliance we would rather show the native theme than a
    half-styled wizard, and the operator should never see the parse warning
    (#886). Returns True if the sheet was applied cleanly.
    """
    import logging

    from PyQt5 import QtCore

    failures: list[str] = []
    previous_handler = None

    def _capture(mode, context, message):
        if "Could not parse stylesheet" in message:
            failures.append(message)
            return  # swallow: this is our problem to handle, not the operator's
        if previous_handler is not None:
            previous_handler(mode, context, message)

    try:
        previous_handler = QtCore.qInstallMessageHandler(_capture)
    except Exception:  # noqa: BLE001 — never let styling break startup
        widget.setStyleSheet(qss)
        return True

    try:
        widget.setStyleSheet(qss)
    finally:
        try:
            QtCore.qInstallMessageHandler(previous_handler)
        except Exception:  # noqa: BLE001
            pass

    if failures:
        logging.getLogger(__name__).warning(
            "Stylesheet rejected by this Qt build (%s) — falling back to native styling",
            failures[0].strip(),
        )
        try:
            widget.setStyleSheet("")
        except Exception:  # noqa: BLE001
            pass
        return False
    return True


def message_box_qss() -> str:
    """Application-wide parser-safe QMessageBox/QInputDialog styling."""
    return (
        "QMessageBox, QInputDialog { background-color: white;"
        " font-family: 'Inter Tight'; }"
        "QMessageBox QLabel, QInputDialog QLabel { color: #1A1A1A;"
        " font-size: 14px; font-family: 'Inter Tight';"
        " min-width: 340px; min-height: 30px; padding: 6px 8px; }"
        "QInputDialog QLineEdit {"
        f" border: 1px solid {FIELD_BD}; border-radius: 8px; padding: 8px 12px;"
        f" font-size: 14px; font-family: 'Segoe UI'; background: {FIELD_BG}; color: #111; }}"
        f"QInputDialog QLineEdit:focus {{ border: 2px solid {BRAND_MID}; }}"
        "QMessageBox QPushButton, QInputDialog QPushButton {"
        " background: white; border: 1px solid #DCDEDB; border-radius: 9px;"
        " padding: 7px 16px; min-width: 90px; min-height: 36px;"
        f" {_font_qss(13, weight='bold')} color: {SECONDARY}; }}"
        "QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {"
        f" background: #F6F7F5; border-color: #C8CAC6; color: {BRAND_DARK}; }}"
        "QMessageBox QPushButton:pressed, QInputDialog QPushButton:pressed {"
        " background: #EBEBEB; }"
        "QMessageBox QPushButton:default, QInputDialog QPushButton:default {"
        " background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
        f" stop:0 {BRAND_MID}, stop:1 {BRAND_DARK}); border: none; color: white; }}"
        "QMessageBox QPushButton:default:hover, QInputDialog QPushButton:default:hover {"
        f" background: {BRAND_MID}; }}"
        "QMessageBox QPushButton:default:pressed, QInputDialog QPushButton:default:pressed {"
        f" background: {BRAND_DARK}; }}"
    )


def apply_shadow(widget, blur: int = 40, offset=(0, 8), color=(20, 35, 18, 46)):
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import QGraphicsDropShadowEffect

    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(blur)
    shadow.setOffset(*offset)
    shadow.setColor(QColor(*color))
    widget.setGraphicsEffect(shadow)
    return shadow


def _render_icon(renderer, size: int, color: str | None):
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap

    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    if color is not None:
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pix.rect(), QColor(color))
    painter.end()
    return QIcon(pix)


def svg_icon(svg_path, size: int = 18, color: str | None = None):
    from PyQt5.QtSvg import QSvgRenderer
    return _render_icon(QSvgRenderer(str(svg_path)), size, color)


def svg_icon_from_markup(markup: str, size: int = 14, color: str | None = None):
    from PyQt5.QtCore import QByteArray
    from PyQt5.QtSvg import QSvgRenderer
    return _render_icon(QSvgRenderer(QByteArray(markup.encode('utf-8'))), size, color)
