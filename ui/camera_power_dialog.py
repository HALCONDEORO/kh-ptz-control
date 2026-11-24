"""Shared nonblocking, touch-sized camera power confirmation."""
from PyQt5.QtWidgets import QMessageBox
from ui.message_box_layout import fit_message_box_buttons


def build_camera_power_dialog(parent, *, power_on=True):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle('Camera start-up' if power_on else 'Camera standby')
    box.setText('Turn on the cameras now?' if power_on else 'Put the cameras in standby now?')
    box.setInformativeText(
        'Start the session and turn on the cameras, or leave them as they are.' if power_on else
        'End the session and put both cameras in standby, or leave them as they are.')
    yes = box.addButton('Turn on cameras' if power_on else 'Put cameras in standby', QMessageBox.AcceptRole)
    no = box.addButton('Not now', QMessageBox.RejectRole)
    fit_message_box_buttons(box)
    for button in (yes, no):
        button.setMinimumHeight(max(52, button.minimumHeight()))
        button.setMinimumWidth(max(220, button.minimumWidth()))
    box.setStyleSheet('QMessageBox { font-size: 18px; } '
                      'QPushButton { font-size: 16px; padding: 10px 16px; }')
    box.setDefaultButton(no)
    box.setEscapeButton(no)
    return box, yes
