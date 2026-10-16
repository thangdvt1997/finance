from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .reputation import Thresholds


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


def _rss_feeds(raw: str | None) -> list[dict]:
    """EC_RSS_FEEDS khong dat -> danh sach mac dinh da kiem chung (default_feeds); dat (ke ca '[]') -> dung dung gia tri do."""
    if raw is None:
        from .default_feeds import DEFAULT_RSS_FEEDS
        return [dict(f) for f in DEFAULT_RSS_FEEDS]
    return json.loads(raw or "[]")


@dataclass
class ECConfig:
    sources: list[str] = field(default_factory=lambda: ["rss_ideas", "static_json", "opinion_feeds"])
    poll_seconds: float = 300
    http_min_interval: float = 2.0
    http_cache_ttl: float = 120
    respect_robots: bool = True
    rss_feeds: list[dict] = field(default_factory=list)
    static_json_path: str = ""
    mql5_accept_tos: bool = False
    mql5_urls: list[str] = field(default_factory=list)
    myfxbook_email: str = ""
    myfxbook_password: str = ""
    thresholds: Thresholds = field(default_factory=Thresholds)
    consensus_min_experts: int = 3
    consensus_min_ratio: float = 0.7
    stance_window_hours: float = 72
    consensus_min_weight: float = 0.0          # 0 = dung min_experts (trong so deu 1 -> hanh vi cu)
    consensus_min_weight_ratio: float = 0.0    # 0 = dung consensus_min_ratio
    track_weights_enabled: bool = True
    track_max_age_hours: float = 72
    dedupe_ttl_seconds: int = 7 * 86400
    opinion_min_credibility: float = 40.0
    cot_consensus: bool = True
    opinion_disable: set = field(default_factory=set)
    sources_dir: str = ""

    @classmethod
    def from_env(cls) -> "ECConfig":
        g = os.getenv
        return cls(
            sources=_csv("EC_SOURCES", "rss_ideas,static_json,opinion_feeds"),
            poll_seconds=float(g("EC_POLL_SECONDS", "300")),
            http_min_interval=float(g("EC_HTTP_MIN_INTERVAL", "2.0")),
            http_cache_ttl=float(g("EC_HTTP_CACHE_TTL", "120")),
            respect_robots=_b("EC_RESPECT_ROBOTS", True),
            rss_feeds=_rss_feeds(g("EC_RSS_FEEDS")),
            static_json_path=g("EC_STATIC_JSON_PATH", ""),
            mql5_accept_tos=_b("EC_MQL5_ACCEPT_TOS", False),
            mql5_urls=_csv("EC_MQL5_URLS", ""),
            myfxbook_email=g("MYFXBOOK_EMAIL", ""),
            myfxbook_password=g("MYFXBOOK_PASSWORD", ""),
            thresholds=Thresholds(
                min_months=float(g("EC_MIN_MONTHS", "6")),
                max_drawdown_pct=float(g("EC_MAX_DRAWDOWN_PCT", "40")),
                min_gain_pct=float(g("EC_MIN_GAIN_PCT", "0")),
                min_followers=int(g("EC_MIN_FOLLOWERS", "0")),
                min_score=float(g("EC_MIN_SCORE", "50")),
                reject_martingale=_b("EC_REJECT_MARTINGALE", True),
            ),
            consensus_min_experts=int(g("EC_CONSENSUS_MIN_EXPERTS", "3")),
            consensus_min_ratio=float(g("EC_CONSENSUS_MIN_RATIO", "0.7")),
            stance_window_hours=float(g("EC_STANCE_WINDOW_HOURS", "72")),
            opinion_min_credibility=float(g("EC_OPINION_MIN_CRED", "40")),
            cot_consensus=_b("EC_COT_CONSENSUS", True),
            opinion_disable=set(_csv("EC_OPINION_DISABLE", "")),
            sources_dir=g("EC_SOURCES_DIR", ""),
            consensus_min_weight=float(g("EC_CONSENSUS_MIN_WEIGHT", "0")),
            consensus_min_weight_ratio=float(g("EC_CONSENSUS_MIN_WEIGHT_RATIO", "0")),
            track_weights_enabled=_b("EC_TRACK_WEIGHTS", True),
            track_max_age_hours=float(g("EC_TRACK_MAX_AGE_HOURS", "72")),
        )
