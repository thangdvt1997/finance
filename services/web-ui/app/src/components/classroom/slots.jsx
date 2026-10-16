// Điểm gắn (slot) cho các thành phần do agent khác viết. KHÔNG import cứng: dùng import.meta.glob để build không lỗi khi tệp chưa có.
// Tên tệp quy ước (cùng thư mục): GuidePanel, DemoPlayer, Tour, Checklist, TemplatePicker  (.jsx, export default).
// Props thống nhất: { lang, rid, profile, canvas, onClose, onSend(text) } (+ extra tuỳ slot, xem README cuối Classroom.jsx / báo cáo).
import { Component, Suspense, lazy } from "react";

const LOADERS = import.meta.glob(["./GuidePanel.jsx", "./DemoPlayer.jsx", "./Tour.jsx", "./Checklist.jsx", "./TemplatePicker.jsx"]);
const cache = {};
export const hasSlot = (name) => !!LOADERS[`./${name}.jsx`];
const getLazy = (name) => (cache[name] ??= lazy(LOADERS[`./${name}.jsx`]));

class Boundary extends Component {
  state = { err: null };
  static getDerivedStateFromError(err) { return { err }; }
  componentDidCatch() { /* không ghi log nội dung nhạy cảm */ }
  render() { return this.state.err ? (this.props.quiet ? null : this.props.fallback) : this.props.children; }
}

/** <Slot name="DemoPlayer" fallback={node} quiet {...props} />: tệp chưa có hoặc lỗi -> fallback (quiet: không hiện gì). */
export function Slot({ name, fallback = null, quiet = false, ...props }) {
  if (!hasSlot(name)) return quiet ? null : fallback;
  const C = getLazy(name);
  return (
    <Boundary fallback={fallback} quiet={quiet} key={name}>
      <Suspense fallback={quiet ? null : <p className="m-0 p-3 text-[12.5px] text-muted" role="status">…</p>}>
        <C {...props} />
      </Suspense>
    </Boundary>
  );
}
