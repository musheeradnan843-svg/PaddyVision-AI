"""Paths for prediction artifacts kept outside the frontend watcher."""

import os
from pathlib import Path

import api.config  # Load project-local .env before reading runtime settings.


def get_runtime_data_dir() -> Path:
    override = os.getenv("PADDYVISION_RUNTIME_DIR")
    if override:
        root = Path(override).expanduser()
    else:
        local_app_data = os.getenv("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        root = base / "PaddyVisionAI"
    root.mkdir(parents=True, exist_ok=True)
    return root
