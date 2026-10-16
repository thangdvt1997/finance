"""Registry plugin: bat/tat nguon qua env (EC_SOURCES). Nguon rui ro ToS can them co xac nhan."""
from __future__ import annotations

import logging

from .config import ECConfig
from .httpclient import PoliteClient
from .sources.base import ExpertSource
from .sources.mql5 import Mql5Source
from .sources.myfxbook import MyfxbookSource
from . import providers_htmllist  # noqa: F401  (dang ky kind html_list)
from .sources.opinion_feeds import OpinionFeedsSource
from .sources.rss_ideas import RssIdeasSource
from .sources.static_json import StaticJsonSource

log = logging.getLogger(__name__)

# ten -> (factory(cfg, client) | None neu bi chan, mo ta)
KNOWN = ("rss_ideas", "static_json", "mql5", "myfxbook", "opinion_feeds")


def build_sources(cfg: ECConfig, client: PoliteClient) -> list[ExpertSource]:
    out: list[ExpertSource] = []
    for name in cfg.sources:
        if name == "rss_ideas":
            out.append(RssIdeasSource(client, cfg.rss_feeds))
        elif name == "static_json":
            out.append(StaticJsonSource(cfg.static_json_path))
        elif name == "opinion_feeds":
            from pathlib import Path

            from .sources_loader import load_all
            entries, stats, errs = load_all(Path(cfg.sources_dir) if cfg.sources_dir else None, set(cfg.opinion_disable))
            log.info("opinion_feeds: %s (loi schema: %d)", stats, len(errs))
            out.append(OpinionFeedsSource(client, entries))
        elif name == "mql5":
            if not cfg.mql5_accept_tos:
                log.warning("mql5 duoc bat trong EC_SOURCES nhung thieu EC_MQL5_ACCEPT_TOS=true -> BO QUA")
                continue
            out.append(Mql5Source(client, cfg.mql5_urls, True))
        elif name == "myfxbook":
            if not (cfg.myfxbook_email and cfg.myfxbook_password):
                log.warning("myfxbook thieu MYFXBOOK_EMAIL/PASSWORD -> BO QUA")
                continue
            out.append(MyfxbookSource(client, cfg.myfxbook_email, cfg.myfxbook_password))
        else:
            log.warning("nguon khong biet: %s (co: %s)", name, ",".join(KNOWN))
    return out
