# Manual ATEM room acceptance

Scope: Admin manually selects Preview and presses CUT or AUTO. Program and
Preview are read from the switcher. PTZ remains independent. This checklist
is not evidence of a successful physical installation.

## Software safeguards

- Production input buttons use names reported by the switcher. Demo labels
  such as PC/Platform/Comments are not evidence of physical room wiring.
- No production input buttons appear before input names arrive, or after an
  empty input-name update. Reported names still require a cabling check.
- Manual Preview, CUT and AUTO require Admin. The panel disables those buttons
  while disconnected. The write adapter also rejects a lost live connection.
- CUT/AUTO are deliberate, single operator requests. There is no automatic retry.
- This change does not configure an IP, alter automation defaults, arm the
  dispatcher, move cameras, or write PiP/upstream keyer state. Existing PiP
  controls are outside this change and do not establish hardware support.

## Hardware acceptance: NOT RUN

1. Record exact switcher model, firmware, IP and application version.
2. Identify the physical inputs for Platform and Comments on the multiview.
   Confirm labels against cables, not the application's historical demo map.
3. Confirm ATEM automation and PiP automation are off. Do not arm either.
4. With production output isolated or permission to change it, sign in as Admin.
   Open the manual panel and confirm live Program/Preview and reported names.
5. Select the verified Platform input into Preview. Confirm Preview only changes;
   cameras must not move. Press CUT deliberately and verify physical Program.
6. Repeat for Comments. Test AUTO only after confirming the switcher's current
   transition settings are safe for the room.
7. Disconnect the switcher and verify the panel disables manual writes. Reconnect
   and confirm live state before another deliberate command. Test normal User
   cannot write Preview, CUT or AUTO.

Do not claim PiP acceptance or Raspberry Pi hardware acceptance from local
fixtures, unit tests, or the real-library loopback contract.
