from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import ensure_utc


class StateStore:
    """Luu moc backfill da xong: key 'provider:symbol:tf' -> ISO end. Ghi nguyen tu (tmp + replace)."""

    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        self._d: dict[str, str] = {}
        if self.path and self.path.exists():
            try:
                self._d = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._d = {}

    def get(self, key: str) -> datetime | None:
        v = self._d.get(key)
        return ensure_utc(datetime.fromisoformat(v)) if v else None

    def set(self, key: str, ts: datetime) -> None:
        self._d[key] = ensure_utc(ts).isoformat()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._d), encoding="utf-8")
            tmp.replace(self.path)
