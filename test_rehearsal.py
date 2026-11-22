"""Hardware-free standalone rehearsal contract, with no Qt dependency."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class RehearsalTests(unittest.TestCase):
    def run_rehearsal(self, *args):
        return subprocess.run([sys.executable, "-m", "simulation.rehearsal", *args],
                              cwd=ROOT, text=True, capture_output=True, timeout=10)

    def test_json_is_deterministic_and_fake(self):
        first = self.run_rehearsal("--json")
        second = self.run_rehearsal("--json")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        report = json.loads(first.stdout)
        self.assertFalse(report["hardware_connected"])
        self.assertFalse(report["configuration_written"])
        self.assertEqual(len(report["steps"]), 4)
        for step in report["steps"]:
            self.assertEqual(step["status"]["adapter_type"], "fake")
            self.assertFalse(step["status"]["moving"])
            self.assertEqual(step["status"]["current_preset"], 3)

    def test_readable_output_and_no_config_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = (
                "import os,sys; from pathlib import Path; "
                "os.environ['HOME']=sys.argv[1]; os.environ['KHPTZ_DATA_DIR']=sys.argv[1]; "
                "from simulation.rehearsal import main; main([]); "
                "assert not list(Path(sys.argv[1]).rglob('*'))"
            )
            run = subprocess.run([sys.executable, "-c", probe, directory], cwd=ROOT,
                                 text=True, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("NO-CAMERA REHEARSAL", run.stdout)
            self.assertIn("No GUI", run.stdout)

    def test_audit_guard_blocks_network_in_process(self):
        probe = (
            "import sys,socket; from simulation.rehearsal import deny_network; "
            "sys.addaudithook(deny_network); "
            "socket.socket()"
        )
        run = subprocess.run([sys.executable, "-c", probe], cwd=ROOT,
                             text=True, capture_output=True, timeout=10)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("PermissionError", run.stderr)

    def test_no_camera_address_option(self):
        run = self.run_rehearsal("--camera", "example.invalid")
        self.assertEqual(run.returncode, 2)


if __name__ == "__main__":
    unittest.main()
