"""Thu adapter Python MetaTrader5 trong Wine (mt5_direct). Dung: py.sh /mtlab/mt5_probe.py [--attach]"""
import MetaTrader5 as mt5, sys
print("package", mt5.__version__, mt5.__author__)
if "--attach" in sys.argv:
    ok = mt5.initialize(timeout=60000)
else:
    ok = mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe", portable=True, timeout=60000)
print("initialize:", ok, mt5.last_error())
if ok:
    ti = mt5.terminal_info()
    print("terminal connected=", ti.connected, "build=", ti.build, "trade_allowed=", ti.trade_allowed, "path=", ti.path)
    print("account_info:", mt5.account_info())
    r = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 5)
    print("rates:", None if r is None else len(r), mt5.last_error())
    mt5.shutdown()
