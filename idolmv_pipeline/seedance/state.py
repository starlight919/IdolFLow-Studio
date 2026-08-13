from __future__ import annotations

import json
from pathlib import Path


class RunState:
    def __init__(self, path: Path, initial: dict | None = None):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else (initial or {})
        if not path.exists():
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))
        temporary.replace(self.path)

    def update(self, **values) -> None:
        self.data.update(values)
        self.save()

    def jobs(self) -> list[dict]:
        return self.data.setdefault("jobs", [])
