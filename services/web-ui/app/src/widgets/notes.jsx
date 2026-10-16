import { useEffect, useRef, useState } from "react";
import { StickyNote } from "lucide-react";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "notes", title: "Ghi chú nhanh", icon: StickyNote, group: "Công cụ", desc: "Ghi chú tự lưu cùng workspace (đồng bộ máy chủ, tối đa ~1500 ký tự).",
  defaultSize: { w: 8, h: 8 }, minSize: { w: 4, h: 4 },
  configSchema: [{ key: "text", label: "Nội dung", type: "textarea", default: "", max: 1500 }],
};

export default function NotesWidget() {
  const { config, setConfig } = useWidget();
  const [v, setV] = useState(config.text || "");
  const last = useRef(config.text || "");
  useEffect(() => { if ((config.text || "") !== last.current) { last.current = config.text || ""; setV(last.current); } }, [config.text]);
  useEffect(() => {
    if (v === last.current) return;
    const t = setTimeout(() => { last.current = v; setConfig({ text: v || undefined }); }, 600);
    return () => clearTimeout(t);
  }, [v]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="tm-fill">
      <textarea aria-label="Ghi chú" className="flex-1 min-h-0 w-full resize-none bg-transparent border-0 outline-none text-fg p-3 text-[13px] leading-relaxed" placeholder="Gõ ghi chú… (tự lưu)"
        maxLength={1500} value={v} onChange={(e) => setV(e.target.value)} spellCheck={false} />
      <div className="px-3 py-1 text-[11px] text-faint border-t border-line text-right">{v.length}/1500</div>
    </div>
  );
}
