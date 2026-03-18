from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict


def _get_codex_home() -> Path:
    code_home = str(os.environ.get("CODEX_HOME") or "").strip()
    if code_home:
        return Path(os.path.expanduser(code_home))
    home_dir = Path(os.path.expanduser(str(os.environ.get("HOME") or "~")))
    return home_dir / ".codex"


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=".",
        dir=str(path.parent),
        delete=False,
        encoding="utf-8",
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(data, handle, indent=2)
        handle.write("\n")
    try:
        temp_path.chmod(0o600)
    except OSError:
        pass
    temp_path.rename(path)
