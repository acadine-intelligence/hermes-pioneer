"""The trail: one JSON file per round under ``<data>/runs``. Rounds link to the gap they expand."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

_RUN_ID = re.compile(r"r(\d+)")
_GAP_ID = re.compile(r"(r\d+)\.g\d+")


class Trail:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir) / "runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        if not _RUN_ID.fullmatch(run_id or ""):
            raise LookupError(f"no round named {run_id!r}")
        return self.root / f"{run_id}.json"

    def ids(self) -> list[str]:
        found = [p.stem for p in self.root.glob("r*.json") if _RUN_ID.fullmatch(p.stem)]
        return sorted(found, key=lambda s: int(s[1:]))

    def new(self, **fields: Any) -> dict:
        ids = self.ids()
        run_id = f"r{(int(ids[-1][1:]) if ids else 0) + 1}"
        run = {"id": run_id, "signals": [], "gaps": [], "queries": [], "errors": [], "dropped": [], **fields}
        self.save(run)
        return run

    def load(self, run_id: str | None = None) -> dict:
        if not run_id:
            ids = self.ids()
            if not ids:
                raise LookupError("no rounds yet. Start with pioneer_seed.")
            run_id = ids[-1]
        path = self._path(run_id)
        if not path.is_file():
            raise LookupError(f"no round named {run_id!r}")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, run: dict) -> None:
        path = self._path(run["id"])
        run["updated"] = time.time()
        fd, tmp = tempfile.mkstemp(dir=str(self.root), prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(run, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def all(self) -> list[dict]:
        return [self.load(i) for i in self.ids()]

    def find_gap(self, gap_id: str) -> tuple[dict, dict]:
        m = _GAP_ID.fullmatch(gap_id or "")
        if not m:
            raise LookupError(f"no gap named {gap_id!r}. Gap ids look like r1.g2.")
        run = self.load(m.group(1))
        for gap in run["gaps"]:
            if gap["id"] == gap_id:
                return run, gap
        raise LookupError(f"no gap named {gap_id!r}")
