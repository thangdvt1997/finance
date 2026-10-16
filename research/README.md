# research/ - nghiên cứu backtest chiến lược kinh điển (forex, vàng)

Báo cáo: `../docs/research/BACKTEST_STUDY.md`. Chỉ nghiên cứu nội bộ, không đụng service/lệnh thật.

## Chạy từ đầu
```
cd D:\Work\trading-system
.venv\Scripts\pip install -r research\requirements.txt
.venv\Scripts\python research\fetch_data.py     # ECB/Frankfurter (FX), FRED (lãi suất 3M), Yahoo (vàng, bạc, SPY, WTI) -> data/*.parquet
.venv\Scripts\python research\data_quality.py   # results/data_quality.csv
.venv\Scripts\python research\tests_sanity.py   # kiểm chứng engine (nhân quả, khớp giải tích, tín hiệu ngẫu nhiên ~ 0)
.venv\Scripts\python research\run_study.py      # ~80s: results/*.csv, results/summary.md, figures/*.png
```
Đặt `PYTHONUTF8=1` nếu console Windows lỗi mã hoá. Seed cố định `SEED=20261011` trong `run_study.py`.

## File
- `engine.py` engine vector hoá (vol-target, chi phí nửa spread, swap, metrics, block bootstrap, Deflated Sharpe). Không dùng vectorbt (license Commons Clause).
- `strategies.py` tín hiệu: TSMOM, MA, Donchian, carry, RSI2, Bollinger, mua-và-giữ, dịch-thời-gian.
- `pq.py` đọc/ghi Parquet bằng fastparquet (pyarrow bị Application Control chặn `_parquet.dll` trên máy dev).
- `data/` dữ liệu (gitignore); `results/` bảng CSV; `figures/` biểu đồ.
- Yahoo FX không dùng (chất lượng kém, xem báo cáo); FX lấy từ ECB.

## Đa tài sản dài hạn (trend chậm) - `multiasset/`
Báo cáo: `../docs/research/MULTI_ASSET_BACKTEST.md`; cấu hình cho paper-trader: `strategies/slow_trend_multiasset.yaml`. **Chạy trên VPS** (container `python:3.12-slim`, `/root/research`), không chạy trên laptop.
```
cd research/multiasset && ./vps_run.sh build_dataset.py     # tải mã lên VPS + chạy trong container research-run (nice, 6 CPU, 16 GB)
# thứ tự: fetch_multiasset.py -> build_dataset.py -> run_multiasset.py -> analyze_multiasset.py
```
Phụ thuộc trên VPS (`pip install --target /root/research/pylib`): pandas numpy scipy matplotlib pyarrow requests statsmodels quantstats. Nguồn: Yahoo chart API (cần User-Agent), FRED `fredgraph.csv` (không cần key), Frankfurter/ECB. Dữ liệu Parquet ở `/root/research/data` (không vào git); kết quả `results/ma_*.csv`, `ma_analysis.json`; hình `figures/ma_fig*.png`.
- `ma_common.py` danh mục + chi phí; `build_dataset.py` dựng chuỗi excess + bảng chất lượng; `ma_engine.py` tín hiệu/sizing/backtest (tái dùng `engine.py`, `strategies.py`); `run_multiasset.py` cấu hình + lưới độ nhạy; `analyze_multiasset.py` bootstrap, DSR, placebo, LOCO, khủng hoảng, hình.
