import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("migration", SCRIPTS / "migrate-video-registry.py")
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class MigrationQuiesceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = self.root / "fixture.py"
        self.fixture.write_text(
            "import importlib.util,sys\n"
            f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
            f"spec=importlib.util.spec_from_file_location('server', {str(SCRIPTS / 'video-server.py')!r})\n"
            "server=importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(server)\n"
            "server.create_app(sys.argv[2]).run(host='127.0.0.1',port=int(sys.argv[1]))\n"
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        self.log_path = self.root / "server.log"
        self.log = self.log_path.open("wb")
        self.addCleanup(self.log.close)
        self.process = subprocess.Popen([sys.executable, str(self.fixture), str(port), str(self.root / "test.sqlite3")],
                                        stdout=self.log, stderr=self.log)
        self.addCleanup(self.stop_fixture)
        deadline = time.monotonic() + 5
        while True:
            try:
                with urlopen(self.base + "/health", timeout=0.2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    self.fail("fixture did not start")
                time.sleep(0.02)
        self.video = self.root / "demo.mp4"
        self.video.write_bytes(b"test")
        self.registered = self.register(self.video)

    def stop_fixture(self):
        if self.process.poll() is None:
            os.kill(self.process.pid, signal.SIGCONT)
            self.process.terminate()
            self.process.wait(timeout=5)

    def register(self, path):
        request = Request(self.base + "/register?" + urlencode({"file": str(path)}), method="POST")
        with urlopen(request, timeout=2) as response:
            return json.load(response)

    def quiesce(self):
        return migration.quiesce_live(self.process.pid, self.root / "snapshot.json", expected_source=str(self.fixture),
                                     base_url=self.base)

    def test_freezes_exact_process_after_capturing_deleted_live_log(self):
        self.log_path.unlink()
        result = self.quiesce()
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["attempts"], 1)
        state = Path(f"/proc/{self.process.pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        self.assertEqual(state, "T")
        data = json.loads((self.root / "snapshot.json").read_text())
        self.assertEqual(data["videos"][0]["secret_id"], self.registered["secret_id"])

    def test_registration_during_capture_resumes_and_retries(self):
        original = migration.snapshot_live
        calls = []
        extra = self.root / "extra.mp4"
        extra.write_bytes(b"second")

        def capture(output, url):
            data = original(output, url)
            if not calls:
                calls.append(self.register(extra))
            return data

        with patch.object(migration, "snapshot_live", side_effect=capture):
            result = self.quiesce()
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["count"], 2)
        data = json.loads((self.root / "snapshot.json").read_text())
        self.assertEqual({entry["secret_id"] for entry in data["videos"]},
                         {self.registered["secret_id"], calls[0]["secret_id"]})

    def test_missing_log_marker_resumes_server_on_failure(self):
        original = migration.snapshot_live

        def capture(output, url):
            return original(output, self.base + "/list")

        with patch.object(migration, "snapshot_live", side_effect=capture), self.assertRaises(RuntimeError):
            self.quiesce()
        with urlopen(self.base + "/health", timeout=2) as response:
            self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()
