from pathlib import Path

import pytest

from nlp import entities, topics
from nlp.enrich import Enricher
from nlp.models import Sentiment, SentimentEngine

CONFIG = Path(__file__).resolve().parents[1] / "config"


class FakeClf:
    """Mô phỏng model: từ khoá đơn giản, KHÔNG cần ONNX/mạng."""

    def __init__(self, version="fake-en@1"):
        self.version = version
        self.calls: list[list[str]] = []

    def predict(self, texts):
        self.calls.append(list(texts))
        out = []
        for t in texts:
            tl = t.lower()
            s = 0.8 if any(w in tl for w in ("surge", "tăng", "jump", "gain", "beat")) else \
                -0.8 if any(w in tl for w in ("plunge", "giảm", "fall", "miss", "crash")) else 0.0
            lab = "positive" if s > 0 else "negative" if s < 0 else "neutral"
            out.append(Sentiment(s, lab, 0.9 if s else 0.6, self.version))
        return out


@pytest.fixture
def fake_en():
    return FakeClf("fake-en@1")


@pytest.fixture
def enricher(fake_en):
    eng = SentimentEngine({"en": fake_en, "vi": FakeClf("fake-vi@1")})
    rules, prefix = entities.load(CONFIG / "entities.yaml")
    return Enricher(eng, rules, prefix, topics.load(CONFIG / "topics.yaml"), summary=True, summary_min_chars=200)
