"""Chạy gateway dưới cProfile (chỉ cho perf-ws-gw): in top hàm theo tottime sau PROF_S giây rồi thoát. Dùng để tìm nút thắt realtime."""
import cProfile, os, pstats, threading, sys, time
pr = cProfile.Profile()
def dump():
    time.sleep(float(os.getenv("PROF_S", "100")))
    pr.disable()
    pstats.Stats(pr, stream=sys.stdout).sort_stats("tottime").print_stats(30)
    sys.stdout.flush()
    os._exit(0)
threading.Thread(target=dump, daemon=True).start()
from api_gateway.main import main
pr.enable()
main()
