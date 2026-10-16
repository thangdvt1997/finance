from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from tscommon.bus import Bus
from tscommon.http import make_app

from .httpclient import PoliteClient
from .models import NullScorer
from .runner import Runner
from .settings import NewsSettings
from .sources.base import Context
from .calendar_book import load_enrich_config
from .sources.actuals import ActualsSource, build_providers
from .sources.calendar_sources import FairEconomySource, OfficialCalendarSource
from .sources.central_banks import CentralBankCalendarSource
from .sources.fmp_calendar import FmpCalendarSource
from .sources.cot import CotSource
from .sources.gdelt import GdeltSource
from .sources.marketaux import MarketauxSource
from .sources.rss import RssSource
from .sources.sec13f import Sec13FSource
from .symbols import load_rules

log = logging.getLogger("news_collector.app")

# khoang cach toi thieu giua 2 request toi cung host (giay)
HOST_INTERVALS = {
    "api.gdeltproject.org": 6.0,                 # GDELT: 1 req/5s toan cuc (hang doi duy nhat theo host, +20% du phong)
    "data.sec.gov": 0.15, "www.sec.gov": 0.15,   # SEC: toi da 10 req/s
    "nfs.faireconomy.media": 10.0,
    "publicreporting.cftc.gov": 1.0,
    "www.bls.gov": 2.0,
    "www.ecb.europa.eu": 3.0, "www.bankofengland.co.uk": 3.0, "www.boj.or.jp": 3.0,
    "financialmodelingprep.com": 2.0,
    "api.marketaux.com": 10.0,
    # nguon 'actual' (API thong ke cong khai)
    "api.bls.gov": 5.0, "www150.statcan.gc.ca": 2.0, "www.ons.gov.uk": 3.0, "data.api.abs.gov.au": 3.0,
    "ec.europa.eu": 3.0, "api.stlouisfed.org": 1.0, "www.stat-search.boj.or.jp": 3.0,
}


def build_sources(cfg: NewsSettings):
    s = []
    if cfg.src_rss:
        s.append(RssSource(cfg.rss_interval))
    if cfg.src_gdelt:
        s.append(GdeltSource(cfg.gdelt_interval))
    if cfg.src_cal_official:
        s.append(OfficialCalendarSource(cfg.cal_interval))
    if cfg.src_cal_central_banks:
        s.append(CentralBankCalendarSource(cfg.cb_interval))
    if cfg.src_cal_fmp:
        if cfg.fmp_api_key:
            s.append(FmpCalendarSource(cfg.fmp_api_key, cfg.cal_interval))
        else:
            log.warning("NC_SRC_CAL_FMP bat nhung thieu FMP_API_KEY -> bo qua nguon cal_fmp")
    if cfg.src_cal_faireconomy:
        s.append(FairEconomySource(cfg.cal_interval))
    if cfg.src_cal_actuals:
        enrich = load_enrich_config(cfg.config_dir)
        s.append(ActualsSource(build_providers(enrich, cfg.bls_api_key, cfg.fred_api_key)))
    if cfg.src_marketaux and cfg.marketaux_token:
        s.append(MarketauxSource(cfg.marketaux_token, cfg.marketaux_interval, cfg.marketaux_daily_budget))
    if cfg.src_cot:
        s.append(CotSource(cfg.cot_interval))
    if cfg.src_sec13f:
        s.append(Sec13FSource(cfg.sec13f_interval))
    return s


def source_status(cfg: NewsSettings, active: list) -> list[dict]:
    """Trang thai nguon tuy chon can key: active | needs_key | disabled (khong chua gia tri bi mat)."""
    names = {x.name for x in active}

    def st(name: str, on: bool, has_key: bool) -> str:
        return "active" if name in names else ("disabled" if not on else ("needs_key" if not has_key else "disabled"))

    return [
        {"provider": "news_marketaux", "state": st("news_marketaux", cfg.src_marketaux, bool(cfg.marketaux_token)),
         "env": ["MARKETAUX_TOKEN"], "needs_env": [] if cfg.marketaux_token else ["MARKETAUX_TOKEN"],
         "signup": "https://www.marketaux.com/register", "limit": "100 req/ngay, 3 bai/req (tu gioi han %d/ngay)" % cfg.marketaux_daily_budget,
         "kind": "news"},
        {"provider": "cal_fmp", "state": st("cal_fmp", cfg.src_cal_fmp, bool(cfg.fmp_api_key)),
         "env": ["FMP_API_KEY", "NC_SRC_CAL_FMP=true"], "needs_env": ([] if cfg.fmp_api_key else ["FMP_API_KEY"]) if cfg.src_cal_fmp else [],
         "signup": "https://site.financialmodelingprep.com/register", "limit": "250 req/ngay (chua xac minh calendar co trong goi free)",
         "kind": "calendar"},
        {"provider": "cal_actuals:fred", "state": "active" if cfg.fred_api_key and cfg.src_cal_actuals else ("needs_key" if cfg.src_cal_actuals else "disabled"),
         "env": ["FRED_API_KEY"], "needs_env": [] if cfg.fred_api_key else ["FRED_API_KEY"],
         "signup": "https://fred.stlouisfed.org/docs/api/api_key.html", "limit": "120 req/phut (tu gioi han 500/ngay)", "kind": "calendar"},
    ]


def build_runner(cfg: NewsSettings, bus: Bus, transport=None, scorer=None) -> Runner:
    client = PoliteClient(cfg.user_agent, HOST_INTERVALS, default_interval=1.0, transport=transport,
                          strict_hosts={"api.gdeltproject.org"})
    ctx = Context(client=client, rules=load_rules(cfg.config_dir / "symbol_map.yaml"), config_dir=cfg.config_dir,
                  user_agent=cfg.user_agent, now=lambda: datetime.now(timezone.utc), scorer=scorer or NullScorer())
    name = cfg.base.service_name if cfg.base.service_name != "unknown" else "news-collector"
    return Runner(bus, ctx, build_sources(cfg), cfg.alert_window_min, cfg.alert_check_interval, cfg.dedupe_ttl, name,
                  risk_enabled=cfg.risk_enabled)


def create_app(cfg: NewsSettings | None = None, bus: Bus | None = None, start_runner: bool = True):
    cfg = cfg or NewsSettings()
    app = make_app("news-collector", internal_auth=True)
    bus = bus or Bus.from_url(cfg.base.redis_url)
    runner = build_runner(cfg, bus)
    app.state.runner = runner

    @asynccontextmanager
    async def lifespan(_app):
        if start_runner and cfg.base.enabled:
            runner.start()
        yield
        await runner.stop()
        await runner.ctx.client.aclose()

    app.router.lifespan_context = lifespan

    @app.get("/providers")
    async def providers():
        """Nguon tuy chon can key mien phi: active | needs_key | disabled."""
        items = source_status(cfg, runner.sources)
        mx = next((x for x in runner.sources if x.name == "news_marketaux"), None)
        for it in items:
            if it["provider"] == "news_marketaux" and mx:
                it["usage"] = mx.info()
            st = runner.status.get(it["provider"])
            it["last_ok"] = st["last_ok"] if st else None
            it["last_error"] = st["last_error"] if st else None
        return {"providers": items, "free_pack": True}

    @app.get("/status")
    async def status():
        act = next((x for x in runner.sources if x.name == "cal_actuals"), None)
        return {"sources": runner.status, "calendar_cached": len(runner.calendar_cache), "calendar": runner.book.stats(),
                "actuals": ({"filled": act.last["filled"], "last_error": act.last["last_error"],
                             "providers": {n: {"calls_today": p.calls, "daily_cap": p.daily_cap} for n, p in act.providers.items()}}
                            if act else None),
                "risk_alerts": runner.risk_enabled}

    return app
