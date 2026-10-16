import os
from pathlib import Path

import pytest
from conftest import FakeClf

from nlp.models import (LEXICON_VERSION, REGISTRY, LexiconClassifier, OnnxClassifier, SentimentEngine, _norm_label,
                        build_engine, ensure_files)


def test_lexicon_en_vi():
    lx = LexiconClassifier()
    assert lx.predict_one("Stocks surge to record high as profits beat forecasts", "en").label == "positive"
    assert lx.predict_one("Euro plunges to 17-month low amid recession fears", "en").label == "negative"
    assert lx.predict_one("Cổ phiếu PNJ và Novaland đồng loạt tăng trần", "vi").label == "positive"
    assert lx.predict_one("VN-Index giảm sàn, áp lực bán tháo", "vi").label == "negative"
    s = lx.predict_one("Federal Reserve Board releases results of the survey", "en")
    assert s.label == "neutral" and -1 <= s.score <= 1 and s.model_version == LEXICON_VERSION
    assert lx.predict_one("Giá vàng không giảm", "vi").score >= 0       # phủ định


def test_lexicon_vi_autodetect_without_lang():
    assert LexiconClassifier().predict_one("Giá vàng tăng mạnh").label == "positive"


def test_engine_routing_and_fallback():
    en = FakeClf("fake-en@1")
    eng = SentimentEngine({"en": en, "vi": None})
    assert eng.version_for("en") == "fake-en@1"
    assert eng.version_for(None) == "fake-en@1"            # không rõ ngôn ngữ -> mặc định en
    assert eng.version_for("vi") == LEXICON_VERSION        # chưa có model vi -> từ điển
    assert eng.version_for("fr") == LEXICON_VERSION        # ngôn ngữ khác, không có model_other
    r = eng.predict(["Giá vàng tăng mạnh"], "vi")
    assert r[0].model_version == LEXICON_VERSION and r[0].label == "positive"
    assert eng.loaded == {"en": "fake-en@1"}


def test_engine_model_crash_falls_back():
    class Boom(FakeClf):
        def predict(self, texts):
            raise RuntimeError("onnx lỗi")

    r = SentimentEngine({"en": Boom()}).predict(["Stocks surge"], "en")
    assert r[0].model_version == LEXICON_VERSION


def test_build_engine_missing_models_falls_back(tmp_path):
    eng = build_engine(tmp_path, {"en": "finbert", "vi": "visobert"}, "lexicon", auto_download=False,
                       endpoint="http://invalid.invalid", threads=1, max_len=32)
    assert eng.loaded == {}
    assert eng.version_for("en") == LEXICON_VERSION


def test_ensure_files_needs_download_permission(tmp_path):
    with pytest.raises(FileNotFoundError):
        ensure_files(REGISTRY["finbert"], tmp_path, False, "https://x")


def test_label_normalisation():
    assert [_norm_label(x) for x in ("Positive", "NEG", "neutral")] == ["positive", "negative", "neutral"]


@pytest.mark.skipif(not os.getenv("NLP_TEST_MODEL_DIR"), reason="cần model thật: đặt NLP_TEST_MODEL_DIR (xem scripts/smoke_real.py)")
def test_real_finbert_onnx():
    root = ensure_files(REGISTRY["finbert"], Path(os.environ["NLP_TEST_MODEL_DIR"]), False, "")
    clf = OnnxClassifier(REGISTRY["finbert"], root, 2, 64)
    r = clf.predict(["Euro falls to 17-month low against dollar amid French debt fears", "Nasdaq gains for fourth straight week"])
    assert r[0].label == "negative" and r[1].label == "positive"
