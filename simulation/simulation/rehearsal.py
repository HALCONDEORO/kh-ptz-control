"""Hardware-free camera adapter rehearsal. No GUI, sockets or configuration writes.

Run from the repository root: python3 -m simulation.rehearsal
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys


def deny_network(event, args):
    """Deny networking in this dedicated process, including UDP sends."""
    if event.startswith("socket."):
        raise PermissionError("Networking is disabled in the rehearsal")


def rehearse():
    # Import only the in-memory adapter, never bootstrap/main or discovery.
    from adapters.fake_camera import FakeCamera

    cameras = [FakeCamera(role, role, move_delay_s=0) for role in ("platform", "comments")]
    steps = []
    for camera in cameras:
        if not camera.power_on() or not camera.save_preset(3) or not camera.recall_preset(3):
            raise RuntimeError("Fake camera command failed")
        steps.append({"step": "save_and_recall", "status": asdict(camera.get_status()),
                      "saved_presets": sorted(camera.saved_presets)})
        if not camera.stop():
            raise RuntimeError("Fake stop failed")
        steps.append({"step": "stop", "status": asdict(camera.get_status())})
        if not camera.standby():
            raise RuntimeError("Fake standby failed")
    return {"mode": "in-memory-rehearsal", "hardware_connected": False,
            "configuration_written": False, "steps": steps,
            "limit": "Adapter rehearsal only. No GUI, physical motion, network STOP delivery or hardware validation."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print deterministic simulated results")
    args = parser.parse_args(argv)
    # Hooks cannot be removed: apply only in this standalone command process.
    sys.addaudithook(deny_network)
    report = rehearse()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("KH PTZ CONTROL | NO-CAMERA REHEARSAL")
        print("In-memory fake adapters. No configuration files or camera addresses used.")
        for step in report["steps"]:
            status = step["status"]
            print("{camera_id}: {step}, simulated preset {current_preset}, moving={moving}".format(
                step=step["step"], **status))
        print(report["limit"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
