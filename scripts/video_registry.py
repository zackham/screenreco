import os
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path


def default_registry_path():
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return Path(os.environ.get("SCREENRECO_REGISTRY_PATH", state_home / "screenreco/videos.sqlite3"))


class VideoRegistry:
    def __init__(self, path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        with closing(self.connect()) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS videos (secret_id TEXT PRIMARY KEY, filepath TEXT NOT NULL)")
            connection.execute("CREATE INDEX IF NOT EXISTS videos_filepath ON videos(filepath)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def entries(self):
        with closing(self.connect()) as connection:
            return [dict(secret_id=key, file=path) for key, path in connection.execute(
                "SELECT secret_id, filepath FROM videos ORDER BY rowid"
            )]

    def get(self, secret_id):
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT filepath FROM videos WHERE secret_id = ?", (secret_id,)).fetchone()
        return row[0] if row else None

    def register(self, filepath):
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT secret_id FROM videos WHERE filepath = ? ORDER BY rowid LIMIT 1", (filepath,)
            ).fetchone()
            if row:
                return row[0]
            secret_id = str(uuid.uuid4())
            connection.execute("INSERT INTO videos VALUES (?, ?)", (secret_id, filepath))
        return secret_id

    def import_entries(self, entries):
        if not isinstance(entries, list):
            raise ValueError("videos must be a list")
        records = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("each video must be an object")
            key, path = entry.get("secret_id"), entry.get("file")
            if not isinstance(key, str) or str(uuid.UUID(key)) != key:
                raise ValueError("invalid video UUID")
            if not isinstance(path, str) or not os.path.isabs(path) or "\0" in path:
                raise ValueError("video path must be absolute")
            records.append((key, path))
        added = 0
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            for key, path in records:
                existing = connection.execute("SELECT filepath FROM videos WHERE secret_id = ?", (key,)).fetchone()
                if existing and existing[0] != path:
                    raise ValueError("UUID conflicts with a different registered path")
                if not existing:
                    connection.execute("INSERT INTO videos VALUES (?, ?)", (key, path))
                    added += 1
        return added
