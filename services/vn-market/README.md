# vn-market

Chứng khoán Việt Nam cuối ngày (HOSE/HNX/UPCoM), CHỈ ĐỌC. Nạp từ VNDirect finfo (công khai, không chính thức) + seed vnstock/KBS (ngành, rổ VN30/VN100/HNX30). Chi tiết nguồn, giới hạn, vận hành: `docs/VN_MARKET.md`.

- API nội bộ (không publish cổng; api-gateway proxy `/v1/vn/*`): `/vn/status|rules|session|overview|indices|index/{code}|heatmap|sectors|movers|limits|breadth|liquidity|foreign|screener|symbols|symbol/{code}|events|news`.
- DB: `infra/db/migrations/005_vn_market.sql`, role `ts_vn` (`infra/db/create_vn_role.sh`). Biến: `VN_DB_URL`, `VN_INGEST` (true/false), `VN_MIN_INTERVAL` (0,8 s), `USER_AGENT`.
- Làm mới seed: `tools/refresh_vn_universe.py` (mỗi quý). Test: `sh infra/ops/run_tests.sh vn-market` (trên VPS).
