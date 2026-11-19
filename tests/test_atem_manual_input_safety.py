"""Manual production switching uses live labels and explicit Admin access."""
import os
from pathlib import Path
import subprocess
import sys


def test_manual_panel_permissions_live_names_and_disconnect():
    script = r'''
from types import SimpleNamespace
from unittest.mock import Mock
from PyQt5.QtWidgets import QApplication
from domain.call_set_policy import OperatingMode
from domain.supportability import OperationResult
from ui.atem_admin_panel import AtemAdminPanel
app = QApplication([])
state = dict(connected=True, program_input=8, preview_input=12)
role = [OperatingMode.ADMIN]
commands = Mock()
diag = SimpleNamespace(read_status=lambda: OperationResult.success('status', 'atem', data=state))
panel = AtemAdminPanel(diag, commands, role_provider=lambda: role[0])
assert panel._preview_btns == {}, 'No hardcoded room map before ATEM reports inputs'
assert 'No room mapping assumed' in panel._lbl_inputs.text()
assert panel._lbl_program.text() == 'Program: 8'
assert panel._lbl_preview.text() == 'Preview: 12'
commands.assert_not_called()
panel.update_input_names({8: 'Desk feed', 12: 'Rear camera'})
assert sorted(panel._preview_btns) == [8, 12]
assert panel._preview_btns[12].text() == '12: Rear camera'
commands.set_preview.return_value = OperationResult.success('set_preview', 'atem')
panel._preview_btns[12].click()
commands.set_preview.assert_called_once_with(12, role=OperatingMode.ADMIN)
commands.cut.assert_not_called()
commands.auto.assert_not_called()
for access in OperatingMode:
    role[0] = access
    panel.refresh()
    allowed = access is OperatingMode.ADMIN
    assert panel._btn_cut.isEnabled() is allowed
    assert panel._btn_auto.isEnabled() is allowed
    assert all(b.isEnabled() is allowed for b in panel._preview_btns.values())
role[0] = OperatingMode.ADMIN
state['connected'] = False
panel.refresh()
assert not panel._btn_cut.isEnabled()
assert not panel._btn_auto.isEnabled()
assert not any(b.isEnabled() for b in panel._preview_btns.values())
assert 'disconnected' in panel._btn_cut.toolTip()
commands.reset_mock()
panel._btn_cut.click()
panel._btn_auto.click()
panel._preview_btns[12].click()
assert commands.mock_calls == []
state['connected'] = True
panel.update_input_names({})
assert panel._preview_btns == {}, 'No fallback to an unverified physical mapping'
commands.assert_not_called()
'''
    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
