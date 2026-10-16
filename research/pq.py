"""Đọc/ghi Parquet bằng fastparquet (pyarrow bị Application Control chặn _parquet.dll trên máy dev này).
Chuẩn hoá index về datetime64[ns] để tránh lỗi đơn vị thời gian của fastparquet+pandas 3."""
import pandas as pd
def save(df, path):
    d = df.copy(); d.index = pd.DatetimeIndex(d.index).astype("datetime64[ns]"); d.index.name = "date"
    d.reset_index().to_parquet(path, engine="fastparquet", index=False)
def load(path):
    d = pd.read_parquet(path, engine="fastparquet"); d["date"] = pd.to_datetime(d["date"]).astype("datetime64[ns]")
    return d.set_index("date").sort_index()
