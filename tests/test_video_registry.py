import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from video_registry import VideoRegistry

spec = importlib.util.spec_from_file_location("video_server", SCRIPTS / "video-server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class VideoRegistryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "registry.sqlite3"
        self.video = self.root / "demo with spaces & punctuation.mp4"
        self.video.write_bytes(b"0123456789")
        self.app = server.create_app(self.database)
        self.app.config["TESTING"] = True
        self.app.config["NGROK_URL"] = "https://v.ham.xyz"
        self.client = self.app.test_client()
        self.registry = self.app.config["VIDEO_REGISTRY"]

    def register(self, path=None):
        return self.client.post("/register", query_string={"file": str(path or self.video)})

    def test_fresh_process_keeps_uuid_and_serves_ranges(self):
        registered = self.register().get_json()
        code = "from video_registry import VideoRegistry; import sys; print(VideoRegistry(sys.argv[1]).get(sys.argv[2]))"
        result = subprocess.run([sys.executable, "-c", code, str(self.database), registered["secret_id"]],
                                env={**os.environ, "PYTHONPATH": str(SCRIPTS)}, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), str(self.video))
        restarted = server.create_app(self.database).test_client()
        with restarted.get(f"/v/{registered['secret_id']}", headers={"Range": "bytes=2-5"}) as response:
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.data, b"2345")
            self.assertEqual(response.headers["Content-Range"], "bytes 2-5/10")

    def test_concurrent_duplicate_registration_uses_one_uuid(self):
        def register_once(_):
            return VideoRegistry(self.database).register(str(self.video))
        with ThreadPoolExecutor(max_workers=8) as pool:
            keys = list(pool.map(register_once, range(24)))
        self.assertEqual(len(set(keys)), 1)
        self.assertEqual(len(self.registry.entries()), 1)

    def test_path_alias_does_not_create_duplicate(self):
        first = self.register().get_json()
        alias = self.root / "alias.mp4"
        alias.symlink_to(self.video)
        self.assertEqual(first, self.register(alias).get_json())

    def test_invalid_paths_do_not_register(self):
        cases = [({}, 400), ({"file": ""}, 400), ({"file": str(self.root)}, 400),
                 ({"file": str(self.root / "missing.mp4")}, 404), ({"file": "bad\0path"}, 400)]
        for query, status in cases:
            with self.subTest(query=query):
                self.assertEqual(self.client.post("/register", query_string=query).status_code, status)
        self.assertEqual(self.registry.entries(), [])

    def test_failed_database_write_does_not_return_a_link(self):
        with patch.object(self.registry, "register", side_effect=sqlite3.OperationalError("disk full")):
            response = self.register()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("url", response.get_json())
        self.assertEqual(self.registry.entries(), [])

    def test_import_preserves_legacy_ids_including_duplicate_paths(self):
        entries = [{"secret_id": str(uuid.uuid4()), "file": str(self.video)} for _ in range(2)]
        missing = {"secret_id": str(uuid.uuid4()), "file": str(self.root / "deleted.mp4")}
        entries.append(missing)
        self.assertEqual(self.registry.import_entries(entries), 3)
        self.assertEqual(self.registry.import_entries(entries), 0)
        restarted = VideoRegistry(self.database)
        self.assertEqual(restarted.entries(), entries)
        self.assertEqual(self.register().get_json()["secret_id"], entries[0]["secret_id"])
        self.assertEqual(self.client.get(f"/v/{missing['secret_id']}").status_code, 404)
        self.assertEqual(len(restarted.entries()), 3)

    def test_import_conflict_rolls_back_entire_batch(self):
        original = self.register().get_json()
        new_entry = {"secret_id": str(uuid.uuid4()), "file": str(self.video)}
        conflict = {"secret_id": original["secret_id"], "file": "/different.mp4"}
        with self.assertRaises(ValueError):
            self.registry.import_entries([new_entry, conflict])
        self.assertEqual(self.registry.entries(), [{"secret_id": original["secret_id"], "file": str(self.video)}])

    def test_import_rejects_invalid_entry_without_partial_write(self):
        valid = {"secret_id": str(uuid.uuid4()), "file": str(self.video)}
        for invalid in ({"secret_id": "not-a-uuid", "file": str(self.video)},
                        {"secret_id": str(uuid.uuid4()), "file": "relative.mp4"}, None):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.registry.import_entries([valid, invalid])
        self.assertEqual(self.registry.entries(), [])

    def test_corrupt_registry_is_not_replaced(self):
        corrupted = self.root / "corrupt.sqlite3"
        corrupted.write_bytes(b"corrupted registry")
        with self.assertRaises(sqlite3.DatabaseError):
            server.create_app(corrupted)
        self.assertEqual(corrupted.read_bytes(), b"corrupted registry")

    def test_database_file_is_private(self):
        self.assertEqual(self.database.stat().st_mode & 0o777, 0o600)

    def test_import_cli_preserves_uuid_after_restart(self):
        entries = [{"secret_id": str(uuid.uuid4()), "file": str(self.video)}]
        snapshot = self.root / "snapshot.json"
        snapshot.write_text(json.dumps({"count": 1, "videos": entries}))
        subprocess.run([sys.executable, str(SCRIPTS / "migrate-video-registry.py"), "import",
                        "--snapshot", str(snapshot), "--registry", str(self.database)],
                       check=True, capture_output=True, text=True)
        self.assertEqual(VideoRegistry(self.database).entries(), entries)


if __name__ == "__main__":
    unittest.main()
