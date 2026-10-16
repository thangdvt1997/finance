"""Test bo loc rui ro tin voi su kien THAT (Fair Economy tuan 12-16/10/2026) + ca cac truong hop bien."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tscommon.risk_windows import (affects, load_config, risk_alerts, risk_state, symbol_currencies, widths,
                                   windows_for_symbol)

FIX = Path(__file__).parent / "fixtures" / "ff_week_2026-10-11.json"
IMPACT = {"high": "high", "medium": "med", "low": "low"}
UTC = timezone.utc


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def events():
    out = []
    for i, r in enumerate(json.loads(FIX.read_text(encoding="utf-8"))):
        ts = datetime.fromisoformat(r["date"]).astimezone(UTC)
        out.append({"event_id": f"ff{i}", "source": "faireconomy", "country": r["country"], "title": r["title"],
                    "impact": IMPACT.get(r["impact"].lower(), "low"), "ts": ts.isoformat()})
    return out


CPI = datetime(2026, 10, 14, 12, 30, tzinfo=UTC)  # 08:30 EDT


def test_symbol_currencies(cfg):
    assert symbol_currencies("EURUSD", cfg) == {"EUR", "USD"}
    assert symbol_currencies("XAUUSD", cfg) == {"XAU", "USD"}
    assert symbol_currencies("US:AAPL", cfg) == {"USD"}
    assert symbol_currencies("VN:VNM", cfg) == {"VND"}
    assert symbol_currencies("NAS100", cfg) == {"USD"}
    assert symbol_currencies("???", cfg) == set()


def test_country_mapping_us_vs_eu_vs_vn(cfg):
    us = {"country": "US", "impact": "high", "title": "x", "ts": CPI.isoformat()}
    eu = {**us, "country": "EUR"}
    assert affects(us, "EURUSD", cfg) and affects(us, "XAUUSD", cfg) and affects(us, "US500", cfg) and affects(us, "US:AAPL", cfg)
    assert not affects(us, "EURGBP", cfg) and not affects(us, "VN:VNM", cfg)
    assert affects(eu, "EURUSD", cfg) and affects(eu, "EURGBP", cfg) and not affects(eu, "XAUUSD", cfg)


def test_real_week_cpi_window_boundaries(cfg, events):
    # trong tuan that: CPI/Core CPI Mi 14/10 12:30Z (impact high)
    for now, state in [(CPI - timedelta(minutes=31), "clear"), (CPI - timedelta(minutes=30), "imminent"),
                       (CPI - timedelta(minutes=16), "imminent"), (CPI - timedelta(minutes=15), "active"),
                       (CPI, "active"), (CPI + timedelta(minutes=30), "active"), (CPI + timedelta(minutes=31), "clear")]:
        s = risk_state(events, "EURUSD", now, cfg)
        assert s["state"] == state, (now, s["state"])


def test_minutes_remaining(cfg, events):
    s = risk_state(events, "EURUSD", CPI + timedelta(minutes=10), cfg)
    assert s["in_window"] and s["minutes_to_end"] == 20 and s["window_start"] == CPI - timedelta(minutes=15)
    s2 = risk_state(events, "EURUSD", CPI - timedelta(minutes=20), cfg)
    assert s2["state"] == "imminent" and s2["minutes_to_start"] == 5
    s3 = risk_state(events, "EURUSD", CPI + timedelta(minutes=29, seconds=30), cfg)
    assert s3["minutes_to_end"] == 1  # lam tron len


def test_unrelated_symbol_not_affected(cfg, events):
    # AUD Unemployment 14/10 20:30 EDT = 15/10 00:30Z chi anh huong AUD; EURGBP khong
    aud = datetime(2026, 10, 15, 0, 30, tzinfo=UTC)
    assert risk_state(events, "AUDUSD", aud, cfg)["state"] == "active"
    assert risk_state(events, "EURGBP", aud, cfg)["state"] == "clear"
    assert risk_state(events, "VN:VNM", CPI, cfg)["state"] == "clear"


def test_gold_longer_after_fomc_nfp(cfg):
    fomc = {"event_id": "f", "source": "fed", "country": "US", "title": "FOMC Rate Decision", "impact": "high",
            "ts": "2026-10-28T18:00:00+00:00"}
    t = datetime(2026, 10, 28, 18, 40, tzinfo=UTC)
    assert risk_state([fomc], "XAUUSD", t, cfg)["state"] == "active"       # T+40 < T+45
    assert risk_state([fomc], "EURUSD", t, cfg)["state"] == "clear"        # forex thuong chi toi T+30
    assert widths(fomc, "XAUUSD", cfg) == (15, 45, 30)
    assert widths({**fomc, "title": "CPI m/m"}, "XAUUSD", cfg) == (15, 30, 30)


def test_non_high_and_holiday_ignored(cfg, events):
    n = sum(len(windows_for_symbol(events, s, cfg)) for s in ("EURUSD", "XAUUSD", "USDJPY"))
    assert n > 0
    low = {"event_id": "l", "source": "x", "country": "US", "title": "Bank Holiday", "impact": "high", "ts": CPI.isoformat()}
    assert windows_for_symbol([low], "EURUSD", cfg) == []
    med = {**low, "title": "Retail", "impact": "med"}
    assert windows_for_symbol([med], "EURUSD", cfg) == []
    nocountry = {**low, "title": "IMF", "country": "All"}
    assert windows_for_symbol([nocountry], "EURUSD", cfg) == []


def test_merged_chain_of_windows(cfg):
    a = {"event_id": "a", "source": "s", "country": "US", "title": "A", "impact": "high", "ts": "2026-10-14T12:30:00+00:00"}
    b = {"event_id": "b", "source": "s", "country": "US", "title": "B", "impact": "high", "ts": "2026-10-14T12:50:00+00:00"}
    s = risk_state([a, b], "EURUSD", CPI + timedelta(minutes=10), cfg)
    assert s["window_end"] == datetime(2026, 10, 14, 13, 20, tzinfo=UTC)  # T_b + 30
    assert len(s["current"]) == 2


def test_upcoming_24h_horizon(cfg, events):
    s = risk_state(events, "EURUSD", CPI - timedelta(hours=3), cfg)
    assert s["state"] == "clear" and s["next_window"]["minutes_to_start"] == 165
    titles = {u["title"] for u in s["upcoming"]}
    assert {"CPI m/m", "Core CPI y/y"} <= titles
    far = risk_state(events, "EURUSD", CPI - timedelta(hours=30), cfg)
    assert far["upcoming"] == [] or all(u["window_start"] <= CPI - timedelta(hours=6) for u in far["upcoming"])


def test_alerts_phases_and_grouping(cfg, events):
    pre = risk_alerts(events, CPI - timedelta(minutes=25), cfg)
    cpi_pre = [a for a in pre if a["phase"] == "pre" and "CPI" in a["title"]]
    assert len(cpi_pre) == 1  # 4 su kien CPI cung gio gom thanh 1 alert
    assert "EURUSD" in cpi_pre[0]["symbols"] and "XAUUSD" in cpi_pre[0]["symbols"] and "EURGBP" not in cpi_pre[0]["symbols"]
    assert cpi_pre[0]["level"] == "warn" and "risk-window" in cpi_pre[0]["tags"]
    enter = [a for a in risk_alerts(events, CPI, cfg) if a["phase"] == "enter" and "CPI" in a["title"]]
    assert len(enter) == 1 and "con 30 phut" in enter[0]["body"]
    ex = [a for a in risk_alerts(events, CPI + timedelta(minutes=33), cfg) if a["phase"] == "exit" and "CPI" in a["title"]]
    assert len(ex) == 1 and ex[0]["level"] == "info"
    # khoa dedupe on dinh theo pha -> khong lap giua 2 lan chay
    assert {a["dedupe_key"] for a in risk_alerts(events, CPI, cfg)} == {a["dedupe_key"] for a in risk_alerts(events, CPI + timedelta(minutes=1), cfg)}
    # khong phat exit cho su kien da ket thuc tu lau (restart)
    assert not [a for a in risk_alerts(events, CPI + timedelta(hours=5), cfg) if "CPI" in a["title"]]


def test_group_extra_collapses_across_sources(cfg):
    ev = [{"event_id": "1", "source": "bls", "country": "US", "title": "Employment Situation", "impact": "high",
           "ts": "2026-11-06T13:30:00+00:00", "extra": {"group": "us_employment"}},
          {"event_id": "2", "source": "faireconomy", "country": "USD", "title": "Non-Farm Employment Change", "impact": "high",
           "ts": "2026-11-06T13:30:00+00:00", "extra": {"group": "us_employment"}}]
    al = risk_alerts(ev, datetime(2026, 11, 6, 13, 10, tzinfo=UTC), cfg)
    assert len(al) == 1 and al[0]["phase"] == "pre"
    # vang: T+45 trong alert ket thuc cua so
    assert "T+45" in al[0]["body"]
