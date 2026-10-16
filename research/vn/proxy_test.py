import numpy as np, pandas as pd
from vn_common import *; from vn_engine import *; from vn_strats import *
df = load_raw(); P = Panel(df); idx = pd.read_parquet(DATA / "vn_index_raw.parquet")
lvl, st = build_vni(P, idx); print(st)
print(lvl.resample("YE").last().round(0).to_dict())
