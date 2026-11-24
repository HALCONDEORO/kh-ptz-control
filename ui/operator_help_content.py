"""Offline user help, grounded in the current operator controls.

Sources: right_panel.py, widgets.py, main_window preset dispatch,
call_set_command_policy.py, session_mixin.py, shutdown_intent_dialog.py,
atem_button_state.py and application/runtime_safety_service.py.
No tutorial launches commands; hardware checks still require local rehearsal.
"""

TOPICS = (
    ('Quick start', (
        ('Before use', 'Use the approved installation and the local rehearsal procedure. '
         'Know the physical fallback and the person responsible for recovery.'),
        ('Start deliberately', 'After login, review the camera power-on prompt. '
         'Do not assume that opening the app proves the cameras are ready.'),
        ('Check the real image', 'Select the intended camera, check framing and use '
         'one command at a time. A connected indicator is not proof of movement or stopping.'),
    )),
    ('Choose a camera', (
        ('Select the target', 'Use Platform or Comments in Camera Selection. '
         'Check which button is selected before moving or saving a preset.'),
        ('Check availability', 'If the camera is unavailable, movement controls are disabled. '
         'Do not keep tapping presets while the connection recovers.'),
    )),
    ('Move and zoom', (
        ('Move the selected camera', 'Use the joystick for pan and tilt. '
         'Release it to request STOP for the camera it was moving.'),
        ('Adjust zoom', 'Use the zoom ring or the + and - buttons. '
         'Watch the image and make small adjustments.'),
        ('Understand STOP', 'Joystick release is not an all-camera stop or a promise '
         'to cancel an automatic preset recall. Help offers STOP BOTH CAMERAS. '
         'Check the physical result; delivery can fail without a connection.'),
    )),
    ('Recall a preset', (
        ('1  Choose the camera', 'Select Platform or Comments. Check the intended camera.'),
        ('2  Tap the preset once', 'A short tap recalls the saved position. The camera moves.'),
        ('3  Check the framing', 'Watch the real image. Do not stack repeated commands. '
         'A long press requests SET instead; review before confirming.'),
    )),
    ('Save a preset', (
        ('Choose and frame', 'Select the intended camera and adjust its position. '
         'Saving overwrites the camera preset; it does not just recall it.'),
        ('Request SET', 'Hold the preset for one second to request SET. '
         'USER and ADMIN use the same timing. A right click also requests SET.'),
        ('Review the save', 'For a platform preset, review Save Camera Position and '
         'choose Yes only if the target is correct. No is the default. '
         'Seat and person presets use their selection/confirmation flow. '
         'A hold alone does not approve a save.'),
    )),
    ('Focus and exposure', (
        ('Focus', 'Auto Focus enables automatic focus. One Push AF focuses once and '
         'then returns to manual mode. Manual Focus selects manual mode; '
         'it is not a separate focus adjustment wheel.'),
        ('Exposure', 'Darker and Brighter request one exposure step for the selected camera. '
         'Backlight toggles backlight compensation. Check the actual image and reported value; '
         'do not treat a tap as proof that the camera applied it.'),
    )),
    ('Tips for meetings', (
        ('Before the meeting', 'Rehearse outside live use. Check camera selection, framing '
         'and the local fallback. Do not update software or change credentials during preparation.'),
        ('During use', 'Make one deliberate change at a time. Do not experiment with '
         'presets or connection recovery during a live meeting.'),
        ('At the end', 'Review the close prompt: Keep cameras on leaves them powered; '
         'Use Power off cameras at the top left to request standby after confirmation. Ending a session also requests power off. '
         'Check the physical outcome and follow the local room procedure.'),
    )),
    ('If something fails', (
        ('Stop adding commands', 'Release the joystick and check the real camera. '
         'If movement continues, use STOP BOTH CAMERAS. It does not power off, '
         'move to HOME, end the session or change ATEM.'),
        ('If STOP cannot be confirmed', 'Check both cameras. Use the rehearsed local fallback '
         'and tell the person responsible for recovery. Do not wait for a green indicator '
         'or improvise cable cuts or power cycling.'),
        ('Why ATEM is missing', 'With real equipment the ATEM button is hidden until '
         'the switcher is connected and its current monitor is verified. '
         'In simulation it may remain visible to allow virtual reconnection. '
         'No ATEM button is needed when the room does not use ATEM.'),
        ('Ask for support', 'Record the app version, what you expected, what happened '
         'and the checks tried. Remove names, addresses, passwords and private configuration '
         'before sharing evidence. This help works without Internet.'),
    )),
)
