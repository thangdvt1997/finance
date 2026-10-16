// Hook tính chỉ báo bằng Web Worker (dự phòng: tính đồng bộ nếu không tạo được worker, ví dụ CSP/trình duyệt cũ).
// Trả { values: Map(instId -> values), pending } ; khi dữ liệu/chỉ báo đổi: giữ kết quả cũ cho tới khi worker trả bản mới (không nháy).
import { useEffect, useRef, useState } from "react";
import { compute } from "./indicators";

let worker = null, seq = 0, failed = false;
const waiting = new Map();
function getWorker() {
  if (failed) return null;
  if (worker) return worker;
  try {
    worker = new Worker(new URL("./indWorker.js", import.meta.url), { type: "module" });
    worker.onmessage = (e) => { const cb = waiting.get(e.data.id); if (cb) { waiting.delete(e.data.id); cb(e.data.out); } };
    worker.onerror = () => { failed = true; worker = null; for (const cb of waiting.values()) cb(null); waiting.clear(); };
  } catch { failed = true; worker = null; }
  return worker;
}

export function runIndicators(cols, list, tfSec) {
  return new Promise((resolve) => {
    const w = getWorker();
    const sync = () => {
      const out = {};
      for (const it of list) { try { out[it.id] = compute(it.type, it.params, cols, tfSec); } catch { out[it.id] = null; } }
      resolve(out);
    };
    if (!w) { setTimeout(sync, 0); return; }
    const id = ++seq;
    waiting.set(id, (out) => (out ? resolve(out) : sync()));
    // cols là mảng thường -> structured clone (nhanh với 20k nến x 6 cột)
    w.postMessage({ id, cols, list, tfSec });
  });
}

export function useIndicatorValues(indicators, cols, tfSec) {
  const [state, setState] = useState({ values: new Map(), key: null });
  const ver = useRef(0);
  const listKey = JSON.stringify(indicators.filter((x) => x.visible).map((x) => [x.id, x.type, x.params]));
  useEffect(() => {
    const list = JSON.parse(listKey).map(([id, type, params]) => ({ id, type, params }));
    const my = ++ver.current;
    if (!list.length || cols.n <= 5) { setState({ values: new Map(), key: cols }); return; }
    runIndicators(cols, list, tfSec).then((out) => {
      if (my !== ver.current) return; // đã có yêu cầu mới hơn
      setState({ values: new Map(Object.entries(out)), key: cols });
    });
  }, [listKey, cols, tfSec]);
  return state;
}
