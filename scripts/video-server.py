#!/usr/bin/env python3
import os
import sqlite3
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from video_registry import VideoRegistry, default_registry_path


def create_app(registry_path=None):
    app = Flask(__name__)
    registry = VideoRegistry(registry_path if registry_path is not None else default_registry_path())
    app.config["VIDEO_REGISTRY"] = registry
    app.config["NGROK_URL"] = None

    def public_url(secret_id):
        base = app.config["NGROK_URL"] or "http://localhost:5678"
        return f"{base}/v/{secret_id}"

    @app.errorhandler(sqlite3.Error)
    def registry_error(error):
        app.logger.error("video registry failed: %s", error)
        return jsonify({"error": "Video registry unavailable"}), 503

    @app.route("/health")
    def health():
        registry.entries()
        return "OK"

    @app.route("/set_ngrok_url", methods=["POST"])
    def set_ngrok_url():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("url"), str):
            return jsonify({"error": "No URL provided"}), 400
        app.config["NGROK_URL"] = data["url"].rstrip("/")
        return jsonify({"status": "ok", "url": app.config["NGROK_URL"]})

    @app.route("/register", methods=["POST"])
    def register_video():
        filepath = request.args.get("file")
        if not filepath:
            return jsonify({"error": "No file parameter provided"}), 400
        try:
            path = Path(filepath).expanduser().resolve(strict=True)
            if not path.is_file():
                return jsonify({"error": "Path must be a regular file"}), 400
            if not os.access(path, os.R_OK):
                return jsonify({"error": "File is not readable"}), 400
        except FileNotFoundError:
            return jsonify({"error": "File does not exist"}), 404
        except (OSError, ValueError, RuntimeError):
            return jsonify({"error": "Invalid file path"}), 400
        secret_id = registry.register(str(path))
        return jsonify({"url": public_url(secret_id), "secret_id": secret_id, "file": str(path)})

    @app.route("/v/<secret_id>")
    def serve_video(secret_id):
        filepath = registry.get(secret_id)
        if not filepath or not Path(filepath).is_file():
            return "Video not found", 404
        return send_file(filepath, mimetype="video/mp4", as_attachment=False, download_name=os.path.basename(filepath))

    @app.route("/list")
    def list_videos():
        videos = [{**entry, "url": public_url(entry["secret_id"])} for entry in registry.entries()]
        return jsonify({"videos": videos, "count": len(videos)})

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5678, debug=False)
