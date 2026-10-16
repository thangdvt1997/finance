"""CLI: python -m reporter.cli daily|weekly [--force] [--period YYYY-MM-DD]"""
from __future__ import annotations

import argparse
import asyncio
import json

from tscommon import Bus, setup_logging

from .config import Settings
from .service import Reporter


async def _run(kind: str, force: bool, period: str | None) -> dict:
    cfg = Settings.from_env()
    bus = Bus.from_url(cfg.redis_url) if cfg.redis_url else None
    try:
        return await Reporter(cfg, bus=bus).generate(kind, period, force=force)
    finally:
        if bus is not None:
            await bus.r.aclose()


def main() -> None:
    ap = argparse.ArgumentParser(prog="reporter.cli")
    ap.add_argument("kind", choices=["daily", "weekly"])
    ap.add_argument("--force", action="store_true", help="sinh lại dù đã có file của kỳ này")
    ap.add_argument("--period", help="YYYY-MM-DD (mặc định: kỳ theo lịch gần nhất)")
    a = ap.parse_args()
    setup_logging()
    print(json.dumps(asyncio.run(_run(a.kind, a.force, a.period)), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
