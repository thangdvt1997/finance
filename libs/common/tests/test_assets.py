from datetime import datetime, timezone

from tscommon import assets

UTC = timezone.utc

# symbol dang co trong DB san xuat (2026-10-12) + crypto: moi cai phai thuoc 1 trong 9 class cua hop dong
LIVE = ("AUDUSD EURUSD GBPUSD NZDUSD USDCAD USDCHF USDJPY XAUUSD FRED:DFF FRED:DGS10 FRED:DGS2 FRED:DTWEXBGS FRED:T10YIE "
        "US:AGG US:BNO US:CANE US:CORN US:CPER US:EWA US:EWG US:EWH US:EWJ US:EWQ US:EWU US:EWY US:EWZ US:FEZ US:GLD US:IEF "
        "US:IEI US:INDA US:IWM US:QQQ US:SHY US:SLV US:SOYB US:SPY US:TLT US:UNG US:USO US:VNM US:WEAT VN:FPT VN:VCB VN:VNM "
        "CRYPTO:BTCUSDT CRYPTO:ETHUSDT CRYPTO:SOLUSDT").split()


def test_all_live_symbols_map_to_contract_classes():
    for s in LIVE:
        info = assets.asset_info(s)
        assert info.cls in assets.CLASSES, (s, info.cls)
        assert info.registered, s


def test_expected_classes():
    c = assets.classify
    assert (c("EURUSD"), c("XAUUSD"), c("CRYPTO:BTCUSDT"), c("US:GLD"), c("US:USO"), c("US:SPY"), c("US:EWG")) == \
           ("forex", "metal", "crypto", "metal", "commodity", "index", "etf")
    assert (c("US:AAPL"), c("VN:VNM"), c("US:TLT"), c("FRED:DGS10"), c("FRED:DTWEXBGS"), c("US:VNM")) == \
           ("stock_us", "stock_vn", "bond", "bond", "index", "etf")


def test_unregistered_symbols_use_patterns():
    assert assets.classify("us:xyz") == "stock_us" and assets.asset_info("US:XYZ").registered is False
    assert assets.classify("VN:HPG") == "stock_vn"
    assert assets.classify("EURCAD") == "forex" and assets.asset_info("EURCAD").quote_currency == "CAD"
    assert assets.classify("CRYPTO:PEPEUSDT") == "crypto"
    i = assets.asset_info("CRYPTO:PEPEUSDT")
    assert i.name == "PEPE/USDT" and i.quote_currency == "USDT" and i.session == "crypto_24x7"
    assert assets.classify("WHATEVER") == "other"


def test_precision_and_quote():
    assert assets.asset_info("USDJPY").precision == 3 and assets.asset_info("EURUSD").precision == 5
    assert assets.asset_info("VN:FPT").precision == 0 and assets.asset_info("VN:FPT").quote_currency == "VND"
    assert assets.asset_info("CRYPTO:BTCUSDT").quote_currency == "USDT"
    assert assets.asset_info("EURJPY").quote_currency == "JPY"


def test_class_infos_ordered_and_complete():
    infos = assets.class_infos()
    assert [i["class"] for i in infos if i["class"] != "other"] == list(assets.CLASSES)
    assert all(i["name"] and i["name_en"] for i in infos)


def test_registry_no_duplicates_and_sessions_defined():
    cfg = assets._load()
    for s in assets.registered_symbols():
        assert assets.asset_info(s).session in cfg["sessions"], s
        assert s == s.upper()


def test_crypto_always_open():
    sat = datetime(2026, 10, 10, 3, 0, tzinfo=UTC)  # thu Bay
    assert assets.session_open("crypto_24x7", sat) is True
    assert assets.session_open("fx_24x5", sat) is False
    assert assets.session_open("us_equity", sat) is False


def test_fx_week_window():
    assert assets.session_open("fx_24x5", datetime(2026, 10, 11, 21, 59, tzinfo=UTC)) is False   # CN truoc 22:00
    assert assets.session_open("fx_24x5", datetime(2026, 10, 11, 22, 0, tzinfo=UTC)) is True
    assert assets.session_open("fx_24x5", datetime(2026, 10, 14, 12, 0, tzinfo=UTC)) is True
    assert assets.session_open("fx_24x5", datetime(2026, 10, 9, 22, 0, tzinfo=UTC)) is False    # T6 22:00 dong


def test_us_equity_dst_and_vn_lunch():
    # 2026-10-14 (EDT, UTC-4): 09:30 NY = 13:30 UTC
    assert assets.session_open("us_equity", datetime(2026, 10, 14, 13, 29, tzinfo=UTC)) is False
    assert assets.session_open("us_equity", datetime(2026, 10, 14, 13, 30, tzinfo=UTC)) is True
    # 2026-12-02 (EST, UTC-5): 09:30 NY = 14:30 UTC
    assert assets.session_open("us_equity", datetime(2026, 12, 2, 14, 29, tzinfo=UTC)) is False
    assert assets.session_open("us_equity", datetime(2026, 12, 2, 14, 30, tzinfo=UTC)) is True
    # VN UTC+7: 10:00 local = 03:00 UTC mo; 12:00 local = 05:00 UTC nghi trua; 13:30 local = 06:30 UTC mo
    assert assets.session_open("vn_equity", datetime(2026, 10, 14, 3, 0, tzinfo=UTC)) is True
    assert assets.session_open("vn_equity", datetime(2026, 10, 14, 5, 0, tzinfo=UTC)) is False
    assert assets.session_open("vn_equity", datetime(2026, 10, 14, 6, 30, tzinfo=UTC)) is True
    assert assets.session_open("eod_daily", datetime(2026, 10, 14, 6, 30, tzinfo=UTC)) is None


def test_risk_windows_crypto_has_no_currency_by_default():
    from tscommon.risk_windows import load_config, symbol_currencies
    cfg = load_config()
    assert symbol_currencies("CRYPTO:BTCUSDT", cfg) == set()           # khong khop nham cap forex 6 ky tu
    assert symbol_currencies("EURUSD", cfg) == {"EUR", "USD"}


def test_mt5_generated_catalog():
    assets.reload()
    c = assets.asset_info
    assert c("AUDDKK").cls == "forex" and c("AUDDKK").group == "Exotics" and c("EURUSD").group == "Majors" and c("EURAUD").group == "Minors"
    assert c("XAUEUR").cls == "metal" and c("XAUEUR").registered
    assert c("DE40").cls == "index" and c("DE40").group == "Châu Âu" and c("US500").cls == "index"
    assert c("USDJPY").precision == 3
    assert c("XAUUSD").name_en == "Gold (spot)"      # muc viet tay thang muc sinh
