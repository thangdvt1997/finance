#!/usr/bin/env python
"""Kiểm tra THẬT (cần mạng lần đầu để tải model): nạp model ONNX, chạy 20 tiêu đề mẫu thật, đo độ chính xác + độ trễ.

Chạy trong container tạm (xem README):
  docker run --rm --name nlp-smoke-1 --cpus 4 --memory 6g -v nlp-smoke-models:/models -v $PWD:/src python:3.12-slim \
    sh -c "pip install -q /src/libs/common /src/services/nlp && python /src/services/nlp/scripts/smoke_real.py --models finbert,multi-distilbert,visobert"
Không đụng Redis/DB. Thoát mã 1 nếu model nào được yêu cầu mà không nạp được.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import statistics as st
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rss_mb() -> float:
    try:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:  # noqa: BLE001  (Windows)
        return -1.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="finbert,visobert")
    ap.add_argument("--model-dir", default=os.getenv("NLP_MODEL_DIR", "/models"))
    ap.add_argument("--threads", type=int, default=int(os.getenv("NLP_THREADS", "3")))
    ap.add_argument("--max-len", type=int, default=96)
    ap.add_argument("--repeat", type=int, default=20)
    ap.add_argument("--data", default=str(HERE / "sample_headlines.json"))
    ap.add_argument("--heldout", default=str(HERE / "sample_vi_heldout.json"), help="tập vi giữ riêng (không dùng để chỉnh từ điển)")
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    from nlp.models import REGISTRY, HybridClassifier, LexiconClassifier, OnnxClassifier, ensure_files

    data = json.loads(Path(a.data).read_text(encoding="utf-8"))
    held = json.loads(Path(a.heldout).read_text(encoding="utf-8")) if a.heldout and Path(a.heldout).exists() else []
    report: dict = {"threads": a.threads, "max_len": a.max_len, "n": len(data), "models": {}}
    failed = False

    def evaluate(name: str, predict, items: list[dict]) -> dict:
        t0 = time.perf_counter()
        preds = predict([i["text"] for i in items])
        batch_ms = (time.perf_counter() - t0) * 1000
        ok = sum(p.label == i["label"] for p, i in zip(preds, items))
        nn = [(p, i) for p, i in zip(preds, items) if i["label"] != "neutral"]
        pol = sum(p.label == i["label"] for p, i in nn)
        singles = []
        for _ in range(a.repeat):
            for it in items:
                t = time.perf_counter()
                predict([it["text"]])
                singles.append((time.perf_counter() - t) * 1000)
        big = [i["text"] for i in items] * 4
        t = time.perf_counter()
        for k in range(0, len(big), 32):
            predict(big[k:k + 32])
        thr = len(big) / (time.perf_counter() - t)
        return {
            "n": len(items), "acc3": round(ok / len(items), 3), "acc_polarity": round(pol / max(1, len(nn)), 3),
            "single_ms_p50": round(st.median(singles), 1), "single_ms_p95": round(sorted(singles)[int(len(singles) * .95) - 1], 1),
            "batch20_ms": round(batch_ms, 1), "throughput_items_per_s_b32": round(thr, 1),
            "preds": [(i["text"][:48], i["label"], p.label, round(p.score, 2)) for p, i in zip(preds, items)],
        }

    for lang in ("en", "vi"):
        items = [d for d in data if d["lang"] == lang]
        lex = LexiconClassifier()
        report["models"][f"lexicon/{lang}"] = evaluate("lexicon", lambda t, lang=lang: lex.predict(t, lang), items)
    if held:
        report["models"]["lexicon/vi_heldout"] = evaluate("lexicon", lambda t: lex.predict(t, "vi"), held)

    for name in [m for m in a.models.split(",") if m]:
        spec = REGISTRY[name]
        try:
            t0 = time.perf_counter()
            root = ensure_files(spec, Path(a.model_dir), True, "https://huggingface.co")
            clf = OnnxClassifier(spec, root, a.threads, a.max_len)
            load_s = time.perf_counter() - t0
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {name}: {e}", file=sys.stderr)
            report["models"][name] = {"error": str(e)}
            failed = True
            continue
        size = sum(f.stat().st_size for f in (root).iterdir()) / 1e6
        for lang in ("en", "vi"):
            items = [d for d in data if d["lang"] == lang]
            r = evaluate(name, clf.predict, items)
            r.update(load_s=round(load_s, 1), disk_mb=round(size, 0), rss_mb_peak=round(rss_mb(), 0), version=clf.version)
            report["models"][f"{name}/{lang}"] = r
        if held:
            report["models"][f"{name}/vi_heldout"] = evaluate(name, clf.predict, held)
        hyb = HybridClassifier(clf, LexiconClassifier())
        report["models"][f"{name}+lexfin/vi"] = evaluate(name, hyb.predict, [d for d in data if d["lang"] == "vi"])
        if held:
            report["models"][f"{name}+lexfin/vi_heldout"] = evaluate(name, hyb.predict, held)

    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "preds"} for k, v in report["models"].items()},
                     ensure_ascii=False, indent=1))
    for k, v in report["models"].items():
        if "preds" in v and k.split("/")[0].split("+")[0] in a.models.split(",") and (k.endswith("heldout") or "+" in k):
            print(f"\n== {k}")
            for t, gold, pred, sc in v["preds"]:
                print(f"{'OK ' if gold == pred else 'XX '} gold={gold:8s} pred={pred:8s} {sc:+.2f}  {t}")
    if a.json:
        Path(a.json).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
