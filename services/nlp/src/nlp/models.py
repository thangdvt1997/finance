"""Bộ phân loại sentiment: ONNX Runtime (CPU, int8) + tokenizers; fallback từ điển (VADER + từ vựng tài chính).

Điểm sentiment = P(positive) - P(negative) trong [-1, 1]; nhãn = argmax; confidence = xác suất lớn nhất.
KHÔNG sinh văn bản tự do: chỉ phân loại.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

log = logging.getLogger("nlp.models")

LEXICON_VERSION = "lexicon-vader-fin@1"


@dataclass(frozen=True)
class Sentiment:
    score: float          # -1..1
    label: str            # positive|negative|neutral
    confidence: float     # 0..1
    model_version: str


@dataclass(frozen=True)
class ModelSpec:
    name: str
    repo: str                   # rỗng = ONNX tự xuất, nằm sẵn trong model_dir/<name>/
    files: tuple[str, ...]      # tương đối trong repo; file đầu là model .onnx
    version: str                # ghi vào model_version
    license: str
    note: str = ""


# Xenova/finbert = ProsusAI/finbert đã xuất ONNX (int8 ~110MB). ViSoBERT: scripts/export_onnx.py tạo (cần torch, chạy 1 lần).
REGISTRY: dict[str, ModelSpec] = {
    "finbert": ModelSpec(
        "finbert", "Xenova/finbert",
        ("onnx/model_quantized.onnx", "tokenizer.json", "config.json"),
        "finbert-int8@1", "Apache-2.0 (ProsusAI/finBERT)", "tiếng Anh, tinh chỉnh trên Financial PhraseBank"),
    "multi-distilbert": ModelSpec(
        "multi-distilbert", "lxyuan/distilbert-base-multilingual-cased-sentiments-student",
        ("onnx/model.onnx", "tokenizer.json", "config.json"),
        "mdistilbert-fp32@1", "Apache-2.0", "đa ngữ chung (không chuyên tài chính)"),
    "visobert": ModelSpec(
        "visobert", "", ("model.onnx", "tokenizer.json", "config.json"),
        "visobert-int8@1", "chưa khai báo (5CD-AI/Vietnamese-Sentiment-visobert)", "tiếng Việt, ViSoBERT"),
    "visobert-fp32": ModelSpec(
        "visobert-fp32", "", ("model.onnx", "tokenizer.json", "config.json"),
        "visobert-fp32@1", "chưa khai báo (5CD-AI/Vietnamese-Sentiment-visobert)", "bản fp32 (không lượng tử hoá)"),
}


class Classifier(Protocol):
    version: str

    def predict(self, texts: list[str]) -> list[Sentiment]: ...


def _download(url: str, dest: Path, timeout: float = 120.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "trading-system-nlp/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:   # noqa: S310 (https cố định)
        while chunk := r.read(1 << 20):
            f.write(chunk)
    os.replace(tmp, dest)


def ensure_files(spec: ModelSpec, model_dir: Path, auto_download: bool, endpoint: str) -> Path:
    """Trả thư mục chứa model; tải từ HF nếu thiếu và được phép. Ném FileNotFoundError nếu không có."""
    root = model_dir / spec.name
    for rel in spec.files:
        dest = root / Path(rel).name
        if dest.exists() and dest.stat().st_size > 0:
            continue
        if not (auto_download and spec.repo):
            raise FileNotFoundError(
                f"thiếu {dest} (model {spec.name}); bật NLP_AUTO_DOWNLOAD hoặc chạy scripts/export_onnx.py")
        url = f"{endpoint.rstrip('/')}/{spec.repo}/resolve/main/{rel}"
        log.info("tải %s -> %s", url, dest)
        _download(url, dest)
    return root


def _norm_label(s: str) -> str:
    s = s.lower()
    if s.startswith("pos"):
        return "positive"
    if s.startswith("neg"):
        return "negative"
    if s.startswith("neu"):
        return "neutral"
    return s


class OnnxClassifier:
    def __init__(self, spec: ModelSpec, root: Path, threads: int = 3, max_len: int = 96):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_path = root / Path(spec.files[0]).name
        if not model_path.exists():
            raise FileNotFoundError(model_path)
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, threads)
        so.inter_op_num_threads = 1
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(model_path), so, providers=["CPUExecutionProvider"])
        self.input_names = {i.name for i in self.session.get_inputs()}
        self.tok = Tokenizer.from_file(str(root / "tokenizer.json"))
        cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
        pad_id = int(cfg.get("pad_token_id") or 0)
        self.tok.enable_truncation(max_length=max_len)
        self.tok.enable_padding(pad_id=pad_id, pad_token=self.tok.id_to_token(pad_id) or "[PAD]")
        id2label = {int(k): str(v) for k, v in cfg.get("id2label", {}).items()}
        self.labels = [_norm_label(id2label[i]) for i in sorted(id2label)]
        if not {"positive", "negative"} <= set(self.labels):
            raise ValueError(f"id2label không có positive/negative: {self.labels}")
        self.version = spec.version
        self.name = spec.name

    def probs(self, texts: list[str], temperature: float = 1.0) -> np.ndarray:
        """Xác suất (n, số lớp) theo thứ tự self.labels; temperature>1 làm mềm (hiệu chỉnh)."""
        enc = self.tok.encode_batch(texts)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
        if "token_type_ids" in self.input_names:
            feed["token_type_ids"] = np.zeros_like(ids)
        feed = {k: v for k, v in feed.items() if k in self.input_names}
        logits = self.session.run(None, feed)[0] / max(temperature, 1e-3)
        z = logits - logits.max(axis=1, keepdims=True)
        p = np.exp(z)
        p /= p.sum(axis=1, keepdims=True)
        return p

    def predict(self, texts: list[str]) -> list[Sentiment]:
        if not texts:
            return []
        p = self.probs(texts)
        ip, ineg = self.labels.index("positive"), self.labels.index("negative")
        return [Sentiment(float(r[ip] - r[ineg]), self.labels[int(r.argmax())], float(r.max()), self.version) for r in p]


# ---------------------------------------------------------------- fallback từ điển
def fold(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


# Từ điển tài chính tự biên (KHÔNG chép Loughran-McDonald vì giấy phép thương mại hạn chế); điểm kiểu VADER (-4..4).
FIN_EN = {
    "surge": 2.5, "surges": 2.5, "surged": 2.5, "soar": 2.5, "soars": 2.5, "soared": 2.5, "rally": 2.2, "rallies": 2.2,
    "rebound": 1.8, "rebounds": 1.8, "jump": 1.8, "jumps": 1.8, "jumped": 1.8, "gain": 1.5, "gains": 1.5, "rise": 1.2,
    "rises": 1.2, "rose": 1.2, "higher": 1.0, "beat": 1.6, "beats": 1.6, "upgrade": 1.8, "upgraded": 1.8, "record": 1.0,
    "profit": 1.5, "profits": 1.5, "growth": 1.3, "bullish": 2.2, "boost": 1.6, "recovery": 1.5, "optimism": 1.8,
    "easing": 0.8, "de-escalation": 1.8, "approved": 1.0, "dividend": 1.0,
    "plunge": -2.8, "plunges": -2.8, "plunged": -2.8, "slump": -2.4, "slumps": -2.4, "tumble": -2.4, "tumbles": -2.4,
    "crash": -3.0, "crashes": -3.0, "fall": -1.5, "falls": -1.5, "fell": -1.5, "drop": -1.5, "drops": -1.5,
    "dropped": -1.5, "decline": -1.5, "declines": -1.5, "lower": -1.0, "low": -0.8, "loss": -1.8, "losses": -1.8,
    "miss": -1.6, "misses": -1.6, "missed": -1.6, "downgrade": -1.8, "downgraded": -1.8, "cut": -0.8, "cuts": -0.8,
    "layoffs": -2.0, "recession": -2.6, "crisis": -2.6, "default": -2.5, "bankruptcy": -3.0, "fears": -1.8, "fear": -1.8,
    "warns": -1.5, "warning": -1.5, "bearish": -2.2, "weak": -1.4, "weaker": -1.4, "selloff": -2.2, "sell-off": -2.2,
    "tensions": -1.6, "war": -2.2, "sanctions": -1.6, "probe": -1.2, "fraud": -2.8, "shortage": -1.6, "turmoil": -2.2,
}
# so khớp trên chuỗi đã bỏ dấu; cụm dài ưu tiên
FIN_VI = {
    "tang tran": 3.0, "tang manh": 2.2, "tang": 1.2, "bat manh": 1.8, "but pha": 2.0, "vuot dinh": 2.2, "ky luc": 1.0,
    "loi nhuan": 1.2, "phuc hoi": 1.6, "khoi sac": 1.8, "nang hang": 2.0, "xanh": 1.0, "hoi phuc": 1.5,
    "tich cuc": 1.5, "kha quan": 1.5, "mua rong": 1.0, "co tuc": 1.0,
    "giam san": -3.0, "giam manh": -2.5, "giam": -1.4, "lao doc": -2.6, "sut giam": -2.0, "lo": -1.8, "thua lo": -2.4,
    "ap luc": -1.4, "khung hoang": -2.6, "kho khan": -1.8, "no xau": -2.0, "bat on": -1.8, "ban rong": -1.2,
    "lui ve": -1.4, "chat vat": -1.4, "tieu cuc": -1.6, "canh bao": -1.5, "pha san": -3.0, "gian doan": -1.6,
    "lam phat": -0.6, "sut": -1.5, "ro ri": -1.6,
}
_NEGATORS_VI = ("khong ", "chua ", "khong the ")
_VI_CHARS = re.compile(r"[ạảãàáâậầấẩẫăắằặẳẵéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ]")


class LexiconClassifier:
    """VADER (MIT) + từ vựng tài chính en/vi. Dùng khi chưa tải được model hoặc ngôn ngữ chưa có model."""

    version = LEXICON_VERSION

    def __init__(self) -> None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        self.vader = SentimentIntensityAnalyzer()
        self.vader.lexicon.update(FIN_EN)
        self._vi_re = [(re.compile(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])"), v)
                       for k, v in sorted(FIN_VI.items(), key=lambda kv: -len(kv[0]))]

    def _vi_score(self, text: str) -> float:
        t = fold(text)
        total, n = 0.0, 0
        for rx, val in self._vi_re:
            for m in list(rx.finditer(t)):
                if t[m.start():m.end()].strip() == "":
                    continue                       # đã tính bởi cụm dài hơn
                neg = t[max(0, m.start() - 8):m.start()].endswith(_NEGATORS_VI)
                total += -val if neg else val
                n += 1
                t = t[:m.start()] + " " * (m.end() - m.start()) + t[m.end():]
        return 0.0 if n == 0 else total / (abs(total) + 3.0)

    def predict_one(self, text: str, lang: str | None = None) -> Sentiment:
        is_vi = lang == "vi" or (lang is None and bool(_VI_CHARS.search(text.lower())))
        c = self._vi_score(text) if is_vi else float(self.vader.polarity_scores(text)["compound"])
        label = "positive" if c >= 0.2 else "negative" if c <= -0.2 else "neutral"
        conf = 0.34 + 0.5 * min(1.0, abs(c)) if label != "neutral" else 0.5 - 0.3 * abs(c)
        return Sentiment(round(c, 4), label, round(conf, 4), self.version)

    def predict(self, texts: list[str], lang: str | None = None) -> list[Sentiment]:
        return [self.predict_one(t, lang) for t in texts]


class HybridClassifier:
    """Model tiếng Việt chung (huấn luyện trên review/mạng xã hội) + từ vựng tài chính: khi từ vựng tài chính có tín hiệu
    (tăng/giảm/lỗ/nâng hạng...) thì trộn điểm (mặc định 60% từ vựng), không thì giữ nguyên kết quả model."""

    def __init__(self, model: Classifier, lexicon: LexiconClassifier, w_lex: float = 0.6):
        self.model, self.lex, self.w = model, lexicon, w_lex
        self.version = f"{model.version}+lexfin@1"

    def predict(self, texts: list[str]) -> list[Sentiment]:
        out = []
        for t, m in zip(texts, self.model.predict(texts)):
            lx = self.lex._vi_score(t)
            if lx == 0.0:
                out.append(Sentiment(m.score, m.label, m.confidence, self.version))
                continue
            sc = (1 - self.w) * m.score + self.w * lx
            lab = "positive" if sc >= 0.2 else "negative" if sc <= -0.2 else "neutral"
            out.append(Sentiment(round(sc, 4), lab, round(min(1.0, 0.5 + abs(sc) / 2), 4), self.version))
        return out


class ViCalibrator:
    """Hiệu chỉnh sentiment tiếng Việt cho ViSoBERT (huấn luyện trên review -> hay gán positive tin cậy cao cho câu trung tính).
    1) Câu không chứa từ khoá cảm xúc/tài chính nào (config/vi_cues.yaml) -> neutral.
    2) Có từ khoá: temperature scaling (T) rồi nếu chênh lệch 2 lớp đầu < margin -> neutral.
    Chỉ bọc model VI; EN không đi qua đây."""

    def __init__(self, model: OnnxClassifier, cues: list[str], temperature: float = 1.0, margin: float = 0.0):
        self.model, self.T, self.margin = model, temperature, margin
        self.version = f"{model.version}+vical@1"
        self._rx = re.compile(r"(?<![a-z0-9])(?:" + "|".join(
            re.escape(fold(c)) for c in sorted(set(cues), key=len, reverse=True) if c.strip()) + r")(?![a-z0-9])") if cues else None

    @staticmethod
    def load_cues(path: Path) -> list[str]:
        import yaml
        d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return [str(x) for k in ("positive", "negative") for x in d.get(k, [])]

    def has_cue(self, text: str) -> bool:
        return bool(self._rx and self._rx.search(fold(text)))

    def predict(self, texts: list[str]) -> list[Sentiment]:
        if not texts:
            return []
        P = self.model.probs(texts, self.T)
        labs = self.model.labels
        ip, ineg, ineu = labs.index("positive"), labs.index("negative"), labs.index("neutral") if "neutral" in labs else -1
        out = []
        for t, r in zip(texts, P):
            top2 = np.sort(r)[-2:]
            if not self.has_cue(t) or (top2[1] - top2[0]) < self.margin:
                conf = float(r[ineu]) if ineu >= 0 else 0.5
                out.append(Sentiment(0.0, "neutral", max(conf, 0.5), self.version))
            else:
                out.append(Sentiment(float(r[ip] - r[ineg]), labs[int(r.argmax())], float(r.max()), self.version))
        return out


# ---------------------------------------------------------------- bộ định tuyến theo ngôn ngữ
class SentimentEngine:
    """Chọn model theo `lang`; model chưa có -> từ điển (ghi model_version tương ứng)."""

    def __init__(self, by_lang: dict[str, Classifier | None], other: Classifier | None = None):
        self.by_lang = by_lang
        self.other = other
        self.lexicon = LexiconClassifier()

    def classifier_for(self, lang: str | None):
        k = (lang or "en").lower()[:2]
        if k in self.by_lang:
            return self.by_lang[k]
        return self.other

    def version_for(self, lang: str | None) -> str:
        c = self.classifier_for(lang)
        return c.version if c is not None else LEXICON_VERSION

    def predict(self, texts: list[str], lang: str | None) -> list[Sentiment]:
        c = self.classifier_for(lang)
        if c is None:
            return self.lexicon.predict(texts, lang)
        try:
            return c.predict(texts)
        except Exception:  # noqa: BLE001  model lỗi lúc chạy -> không làm sập pipeline
            log.exception("model %s lỗi, dùng từ điển cho lô này", getattr(c, "version", "?"))
            return self.lexicon.predict(texts, lang)

    @property
    def loaded(self) -> dict[str, str]:
        d = {k: v.version for k, v in self.by_lang.items() if v is not None}
        if self.other is not None:
            d["other"] = self.other.version
        return d


def build_engine(model_dir: Path, names: dict[str, str], other: str, auto_download: bool, endpoint: str,
                 threads: int, max_len: int, vi_hybrid: bool = False, vi_cal: dict | None = None) -> SentimentEngine:
    """names: {'en': 'finbert', 'vi': 'visobert'}. Model nào không tải/mở được -> None (rơi về từ điển)."""
    def load(name: str) -> Classifier | None:
        if name in ("", "lexicon", "none"):
            return None
        spec = REGISTRY.get(name)
        if spec is None:
            log.error("model không có trong REGISTRY: %s", name)
            return None
        try:
            t0 = time.perf_counter()
            root = ensure_files(spec, model_dir, auto_download, endpoint)
            clf = OnnxClassifier(spec, root, threads, max_len)
            log.info("đã nạp %s (%s) trong %.1fs", name, spec.version, time.perf_counter() - t0)
            return clf
        except Exception as e:  # noqa: BLE001
            log.warning("không nạp được model %s: %s -> dùng từ điển", name, e)
            return None

    by_lang = {lang: load(n) for lang, n in names.items()}
    vi = by_lang.get("vi")
    if vi_cal and vi_cal.get("enabled") and isinstance(vi, OnnxClassifier):
        try:
            by_lang["vi"] = ViCalibrator(vi, ViCalibrator.load_cues(Path(vi_cal["cues"])), vi_cal["temperature"], vi_cal["margin"])
        except Exception as e:  # noqa: BLE001
            log.warning("không bật hiệu chỉnh VI: %s", e)
    if vi_hybrid and by_lang.get("vi") is not None:
        by_lang["vi"] = HybridClassifier(by_lang["vi"], LexiconClassifier())
    return SentimentEngine(by_lang, load(other))
