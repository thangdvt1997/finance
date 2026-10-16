from paper_trader.config import infer_class, instrument_for, load_yaml


def test_us_etf_is_usd_equity_not_fx():
    cfg = load_yaml(None)
    assert infer_class("US:SPY") == "equity_us"
    i = instrument_for(cfg, "US:SPY")
    assert i.quote == "USD" and i.kind == "equity" and i.shortable and i.lot == 1


def test_fx_and_vn_unchanged():
    cfg = load_yaml(None)
    assert instrument_for(cfg, "USDJPY").quote == "JPY" and infer_class("VN:FPT") == "equity_vn" and infer_class("XAUUSD") == "metal"


def test_crypto_symbol_is_not_mistaken_for_fx_pair():
    cfg = load_yaml(None)
    assert infer_class("CRYPTO:BTCUSDT") == "crypto"
    i = instrument_for(cfg, "CRYPTO:BTCUSDT")
    assert i.quote == "USD" and i.kind == "crypto" and not i.shortable
