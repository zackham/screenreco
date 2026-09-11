#!/usr/bin/env python3
import argparse
import json
import os
import signal
import stat
import tempfile
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

from video_registry import VideoRegistry, default_registry_path


def snapshot_live(output, url="http://127.0.0.1:5678/list"):
    with urlopen(url, timeout=10) as response:
        data = json.load(response)
    if not isinstance(data, dict) or not isinstance(data.get("videos"), list) or data.get("count") != len(data["videos"]):
        raise ValueError("invalid live registry response")
    output = Path(output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=output.parent, prefix=f".{output.name}.")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
        directory_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return data


def process_identity(pid):
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def quiesce_live(pid, output, attempts=5, expected_source="/home/zack/work/screenreco/scripts/video-server.py",
                 base_url="http://127.0.0.1:5678"):
    identity = process_identity(pid)
    argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    if os.fsencode(expected_source) not in argv:
        raise ValueError("PID is not the expected video server")
    # The launcher's log pathname can be deleted while the live descriptor remains valid.
    with open(f"/proc/{pid}/fd/2", "rb", buffering=0) as log:
        if not stat.S_ISREG(os.fstat(log.fileno()).st_mode):
            raise ValueError("server stderr is not a regular access log")
        for attempt in range(1, attempts + 1):
            stopped = False
            try:
                offset = log.seek(0, os.SEEK_END)
                marker = uuid.uuid4().hex
                data = snapshot_live(output, f"{base_url}/list?migration_capture={marker}")
                if process_identity(pid) != identity:
                    raise RuntimeError("server PID changed during capture")
                os.kill(pid, signal.SIGSTOP)
                stopped = True
                deadline = time.monotonic() + 2
                while True:
                    states = [path.read_text().rsplit(")", 1)[1].split()[0]
                              for path in Path(f"/proc/{pid}/task").glob("*/stat")]
                    if states and all(state == "T" for state in states):
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("server threads did not stop")
                    time.sleep(0.01)
                log.seek(offset)
                tail = log.read()
                marker_lines = [line for line in tail.splitlines() if marker.encode() in line]
                if not any(b'" 200 ' in line for line in marker_lines):
                    raise RuntimeError("snapshot request was not observed in the live access log")
                # Start before GET: registration may occur between list construction and its log line.
                if b'"POST ' not in tail:
                    return {"pid": pid, "identity": identity, "count": len(data["videos"]), "attempts": attempt}
            except BaseException:
                if stopped and process_identity(pid) == identity:
                    os.kill(pid, signal.SIGCONT)
                raise
            if stopped and process_identity(pid) == identity:
                os.kill(pid, signal.SIGCONT)
        raise RuntimeError("registration traffic did not quiesce; server resumed")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--output", required=True)
    quiesce = commands.add_parser("quiesce")
    quiesce.add_argument("--pid", type=int, required=True)
    quiesce.add_argument("--output", required=True)
    restore = commands.add_parser("import")
    restore.add_argument("--snapshot", required=True)
    restore.add_argument("--registry", default=default_registry_path())
    args = parser.parse_args()
    if args.command == "quiesce":
        result = quiesce_live(args.pid, args.output)
        print(f"server PID {result['pid']} STOPPED; saved {result['count']} mappings after {result['attempts']} attempt(s)")
        print(f"resume without installing: kill -CONT {result['pid']}")
        return
    if args.command == "snapshot":
        data = snapshot_live(args.output)
        print(f"saved {len(data['videos'])} mappings to {args.output}")
        return
    with Path(args.snapshot).expanduser().open() as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or data.get("count") != len(data.get("videos", [])):
        raise ValueError("invalid snapshot")
    registry = VideoRegistry(args.registry)
    added = registry.import_entries(data["videos"])
    missing = sum(not Path(entry["file"]).is_file() for entry in data["videos"])
    print(f"imported {added} mappings; {len(registry.entries())} total; {missing} backing files missing")


if __name__ == "__main__":
    main()
