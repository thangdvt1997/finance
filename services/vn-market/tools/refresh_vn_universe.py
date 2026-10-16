"""Tạo lại seed `src/vn_market/seed/vn_universe.json` (phân ngành KBS + rổ VN30/VN100/HNX30 + ETF) bằng vnstock 4 (không cần key).

Chạy TRÊN VPS bên trong container market-collector (đã có vnstock 4.0.9), in JSON ra stdout:
    docker exec -i tradingsys-market-collector-1 python - < services/vn-market/tools/refresh_vn_universe.py > seed.json
rồi chép seed.json đè lên src/vn_market/seed/vn_universe.json và commit. VN30 cơ cấu mỗi 6 tháng, VN100/HNX30 mỗi kỳ -> chạy lại mỗi quý.
Giấy phép vnstock: miễn phí cá nhân/học tập/nghiên cứu (xem services/market-collector/README.md). vnstock chỉ dùng để tạo seed, không nằm trong image vn-market.
"""
import datetime
import json
import os

os.environ["VNSTOCK_TELEMETRY"] = "off"
import vnstock  # noqa: E402

L = vnstock.Listing()
ind = L.symbols_by_industries()
out = {
    "_meta": {"source": f"vnstock {getattr(vnstock, '__version__', '4.x')} Listing (KBS) - phân ngành KBS, không phải ICB chính thức",
              "generated": datetime.date.today().isoformat()},
    "industries": {r.symbol: [int(r.industry_code), r.industry_name] for r in ind.itertuples()},
    "groups": {g: sorted(list(L.symbols_by_group(g))) for g in ("VN30", "VN100", "HNX30")},
    "etf": sorted(list(L.all_etf())),
}
print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
