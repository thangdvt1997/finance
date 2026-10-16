// Web Worker tính chỉ báo ngoài luồng giao diện (20.000 nến không làm giật thao tác kéo/zoom).
// Nhận { id, cols, list:[{id,type,params}], tfSec }, trả { id, out:{ [instId]: values | null } }.
import { compute } from "./indicators";

self.onmessage = (e) => {
  const { id, cols, list, tfSec } = e.data;
  const out = {};
  for (const it of list) {
    try { out[it.id] = compute(it.type, it.params, cols, tfSec); } catch { out[it.id] = null; }
  }
  self.postMessage({ id, out });
};
