#!/usr/bin/env python
"""Xuất model HF -> ONNX int8 (một lần, trong container tạm có torch; image chạy KHÔNG chứa torch).

  pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install transformers onnx onnxruntime
  python export_onnx.py --repo 5CD-AI/Vietnamese-Sentiment-visobert --out /models/visobert \
      --labels negative,positive,neutral

Ghi: model.onnx (int8 động), tokenizer.json, config.json (id2label chuẩn hoá + pad_token_id).
Kiểm tra parity logits fp32(torch) vs int8(onnx) trên vài câu.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="5CD-AI/Vietnamese-Sentiment-visobert")
    ap.add_argument("--out", default="/models/visobert")
    ap.add_argument("--labels", default="negative,positive,neutral", help="thứ tự nhãn theo chỉ số logit")
    ap.add_argument("--opset", type=int, default=17)
    ap.add_argument("--no-quant", action="store_true")
    a = ap.parse_args()

    import numpy as np
    import onnxruntime as ort
    import torch
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from transformers import AutoModelForSequenceClassification

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    # Dùng thẳng tokenizer.json của repo (AutoTokenizer bản mới lỗi chuyển đổi vocab Unigram của ViSoBERT).
    tok_path = hf_hub_download(a.repo, "tokenizer.json")
    shutil.copyfile(tok_path, out / "tokenizer.json")
    tk = Tokenizer.from_file(str(out / "tokenizer.json"))
    cfg0 = json.loads(Path(hf_hub_download(a.repo, "config.json")).read_text(encoding="utf-8"))
    pad_id = int(cfg0.get("pad_token_id") or 0)
    tk.enable_padding(pad_id=pad_id, pad_token=tk.id_to_token(pad_id) or "<pad>")
    tk.enable_truncation(max_length=128)

    def encode(texts):
        enc = tk.encode_batch(texts)
        return (torch.tensor([e.ids for e in enc]), torch.tensor([e.attention_mask for e in enc]))

    model = AutoModelForSequenceClassification.from_pretrained(a.repo).eval()
    labels = a.labels.split(",")
    assert len(labels) == model.config.num_labels, (labels, model.config.num_labels)

    sample_ids, sample_mask = encode(["Cổ phiếu tăng trần", "Giá vàng giảm mạnh"])
    names = ["input_ids", "attention_mask"]
    fp32 = Path(tempfile.mkdtemp()) / "model_fp32.onnx"
    with torch.no_grad():
        torch.onnx.export(
            model, (sample_ids, sample_mask), str(fp32), input_names=names,
            output_names=["logits"], opset_version=a.opset, dynamo=False,
            dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}, "logits": {0: "b"}})
    target = out / "model.onnx"
    if a.no_quant:
        shutil.move(str(fp32), str(target))
    else:
        quantize_dynamic(str(fp32), str(target), weight_type=QuantType.QInt8)
    cfg = {"pad_token_id": pad_id, "id2label": {str(i): n for i, n in enumerate(labels)},
           "source_repo": a.repo, "exported_with": "torch.onnx + onnxruntime dynamic int8"}
    (out / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")

    # parity
    texts = ["Cổ phiếu PNJ tăng trần", "Giá vàng giảm mạnh, nhà đầu tư lo ngại", "HoSE cập nhật danh sách cắt margin"]
    ids, mask = encode(texts)
    with torch.no_grad():
        ref = model(input_ids=ids, attention_mask=mask).logits.numpy()
    sess = ort.InferenceSession(str(target), providers=["CPUExecutionProvider"])
    got = sess.run(None, {"input_ids": ids.numpy(), "attention_mask": mask.numpy()})[0]
    print("max |Δlogit| fp32 vs onnx:", float(np.abs(ref - got).max()), "| argmax khớp:",
          bool((ref.argmax(1) == got.argmax(1)).all()), "| size MB:", round(target.stat().st_size / 1e6, 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
