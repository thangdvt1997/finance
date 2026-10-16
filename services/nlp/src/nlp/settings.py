from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from tscommon.config import Settings


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _n(name: str, default: float) -> float:
    return float(os.getenv(name, default))


@dataclass(frozen=True)
class NlpSettings:
    base: Settings = field(default_factory=Settings)
    config_dir: Path = field(default_factory=lambda: Path(os.getenv(
        "NLP_CONFIG_DIR", Path(__file__).resolve().parents[2] / "config")))
    model_dir: Path = field(default_factory=lambda: Path(os.getenv("NLP_MODEL_DIR", "/models")))
    auto_download: bool = field(default_factory=lambda: _b("NLP_AUTO_DOWNLOAD", True))
    hf_endpoint: str = field(default_factory=lambda: os.getenv("NLP_HF_ENDPOINT", "https://huggingface.co"))
    # tên model theo ngôn ngữ (khoá trong models.REGISTRY); "lexicon" = chỉ dùng từ điển
    model_en: str = field(default_factory=lambda: os.getenv("NLP_MODEL_EN", "finbert"))
    model_vi: str = field(default_factory=lambda: os.getenv("NLP_MODEL_VI", "visobert"))
    vi_hybrid: bool = field(default_factory=lambda: _b("NLP_VI_HYBRID", False))
    # hiệu chỉnh sentiment tiếng Việt (ViCalibrator); NLP_VI_CAL=false để tắt
    vi_cal: bool = field(default_factory=lambda: _b("NLP_VI_CAL", True))
    vi_cal_temp: float = field(default_factory=lambda: _n("NLP_VI_CAL_TEMP", 1.0))
    vi_cal_margin: float = field(default_factory=lambda: _n("NLP_VI_CAL_MARGIN", 0.0))
    model_other: str = field(default_factory=lambda: os.getenv("NLP_MODEL_OTHER", "lexicon"))
    threads: int = field(default_factory=lambda: int(_n("NLP_THREADS", 3)))   # intra-op; giữ <= cpus của container
    max_len: int = field(default_factory=lambda: int(_n("NLP_MAX_LEN", 96)))
    batch: int = field(default_factory=lambda: int(_n("NLP_BATCH", 32)))
    queue_max: int = field(default_factory=lambda: int(_n("NLP_QUEUE_MAX", 256)))
    read_block_ms: int = field(default_factory=lambda: int(_n("NLP_READ_BLOCK_MS", 2000)))
    group: str = field(default_factory=lambda: os.getenv("NLP_GROUP", "nlp"))
    consumer: str = field(default_factory=lambda: os.getenv("NLP_CONSUMER", os.getenv("HOSTNAME", "nlp-1")))
    reclaim_idle_ms: int = field(default_factory=lambda: int(_n("NLP_RECLAIM_IDLE_MS", 120_000)))
    model_retry_s: int = field(default_factory=lambda: int(_n("NLP_MODEL_RETRY_S", 600)))
    dedupe_ttl: int = field(default_factory=lambda: int(_n("NLP_DEDUPE_TTL", 30 * 86400)))
    skip_sources: tuple[str, ...] = field(default_factory=lambda: tuple(
        x.strip() for x in os.getenv("NLP_SKIP_SOURCES", "cot,sec13f").split(",") if x.strip()))   # dữ liệu có cấu trúc, không phải văn bản
    summary: bool = field(default_factory=lambda: _b("NLP_SUMMARY", True))
    summary_min_chars: int = field(default_factory=lambda: int(_n("NLP_SUMMARY_MIN_CHARS", 400)))
    # tổng hợp theo symbol + cảnh báo đảo chiều
    alert_enabled: bool = field(default_factory=lambda: _b("NLP_ALERT_ENABLED", True))
    alert_min_delta: float = field(default_factory=lambda: _n("NLP_ALERT_MIN_DELTA", 0.5))
    alert_min_n_1h: int = field(default_factory=lambda: int(_n("NLP_ALERT_MIN_N_1H", 3)))
    alert_min_n_24h: int = field(default_factory=lambda: int(_n("NLP_ALERT_MIN_N_24H", 6)))
    alert_cooldown_s: int = field(default_factory=lambda: int(_n("NLP_ALERT_COOLDOWN_S", 6 * 3600)))
    alert_fresh_s: int = field(default_factory=lambda: int(_n("NLP_ALERT_FRESH_S", 2 * 3600)))  # bỏ qua tin cũ (backfill)
