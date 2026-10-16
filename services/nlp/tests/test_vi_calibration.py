"""Hiệu chỉnh sentiment VI (ViCalibrator). Bộ 40 câu viết tay: tests/data/vi_sentiment_cases.json (split dev/held).
Nếu có model thật (NLP_MODEL_DIR/visobert/model.onnx) thì chạy bằng model thật; không thì dùng logits ĐÃ ĐO
trước đó bằng ViSoBERT int8 thật (tests/data/vi_logits_fixture.json) -> đây là FIXTURE, không phải suy luận trực tiếp."""
import json
import os
from pathlib import Path

import numpy as np
import pytest

from nlp.models import REGISTRY, OnnxClassifier, ViCalibrator

HERE = Path(__file__).parent
CUES = ViCalibrator.load_cues(HERE.parent / "config" / "vi_cues.yaml")
CASES = json.loads((HERE / "data" / "vi_sentiment_cases.json").read_text(encoding="utf-8"))
FIX = json.loads((HERE / "data" / "vi_logits_fixture.json").read_text(encoding="utf-8"))
MODEL_ROOT = Path(os.getenv("NLP_MODEL_DIR", "/models")) / "visobert"
LABS = ["negative", "positive", "neutral"]


class FixtureModel:
    """Trả xác suất từ logits đã đo (không chạy ONNX)."""
    version, labels = "visobert-int8@1", FIX["labels"]

    def probs(self, texts, temperature=1.0):
        z = np.array([FIX["logits"][t] for t in texts]) / temperature
        z -= z.max(axis=1, keepdims=True)
        p = np.exp(z)
        return p / p.sum(axis=1, keepdims=True)


def _model():
    if (MODEL_ROOT / "model.onnx").exists():
        return OnnxClassifier(REGISTRY["visobert"], MODEL_ROOT, 1, 96)
    return FixtureModel()


def _argmax(model, texts):
    return [model.labels[int(i)] for i in model.probs(texts).argmax(axis=1)]


def _macro_f1(ys, ps):
    fs = []
    for lab in ("negative", "neutral", "positive"):
        tp = sum(y == lab and p == lab for y, p in zip(ys, ps))
        fp = sum(y != lab and p == lab for y, p in zip(ys, ps))
        fn = sum(y == lab and p != lab for y, p in zip(ys, ps))
        fs.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(fs) / 3


def test_dataset_shape():
    from collections import Counter
    assert len(CASES) == 40
    assert Counter(c["label"] for c in CASES) == {"neutral": 14, "positive": 13, "negative": 13}
    assert sum(c["split"] == "held" for c in CASES) == 10
    assert all(c["text"] in FIX["logits"] for c in CASES)


@pytest.mark.parametrize("split", ["dev", "held"])
def test_calibration_not_worse_than_baseline(split):
    m = _model()
    cs = [c for c in CASES if c["split"] == split]
    texts, ys = [c["text"] for c in cs], [c["label"] for c in cs]
    base = _macro_f1(ys, _argmax(m, texts))
    cal = ViCalibrator(m, CUES)
    got = _macro_f1(ys, [s.label for s in cal.predict(texts)])
    assert got >= base - 1e-9


def test_known_neutral_sentences():
    m = _model()
    # câu có thật trong QA_ISSUES (NLP-VI); các câu này nằm trong bộ dev, có kiểm nhãn neutral
    texts = ["Hôm nay là thứ ba", "Hôm nay trời mưa",
             "Ngân hàng Nhà nước công bố lịch họp điều hành chính sách tiền tệ"]
    for s in ViCalibrator(m, CUES).predict(texts):
        assert s.label == "neutral" and abs(s.score) < 0.2


def test_cue_sentences_keep_model_polarity():
    m = _model()
    out = ViCalibrator(m, CUES).predict(["Công ty báo lỗ nặng và bị cảnh báo nguy cơ đình chỉ giao dịch",
                                         "VN-Index tăng mạnh, thanh khoản vượt đỉnh nhiều tháng"])
    assert [s.label for s in out] == ["negative", "positive"]


def test_cue_matching_is_word_bounded_and_accent_insensitive():
    cal = ViCalibrator(FixtureModel(), ["lỗ", "tăng"])
    assert cal.has_cue("cổ phiếu tang manh") is True
    assert cal.has_cue("lỗ ròng") is True
    assert cal.has_cue("tăngg") is False
