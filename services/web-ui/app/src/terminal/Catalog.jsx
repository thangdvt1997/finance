// Danh mục widget: tìm theo tên/mô tả, nhóm theo group, bấm để thêm vào workspace hiện tại.
import { useMemo, useState } from "react";
import { Plus, Search } from "lucide-react";
import { Dialog } from "../components/dialog";
import { WIDGET_LIST } from "./registry";

const fold = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();

export default function Catalog({ open, onClose, onAdd }) {
  const [q, setQ] = useState("");
  const groups = useMemo(() => {
    const t = fold(q.trim());
    const list = WIDGET_LIST.filter((w) => !t || fold(`${w.title} ${w.desc} ${w.group} ${w.id}`).includes(t));
    const m = new Map();
    for (const w of list) { if (!m.has(w.group)) m.set(w.group, []); m.get(w.group).push(w); }
    return [...m];
  }, [q]);
  return (
    <Dialog open={open} onClose={onClose} title="Thêm widget" description="Chọn một widget để thêm vào cuối workspace; kéo thả để đặt vị trí." variant="drawer">
      <div className="p-3 grid gap-3">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true" />
          <input data-autofocus className="field w-full !pl-8" placeholder="Tìm widget…" aria-label="Tìm widget" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {groups.length === 0 && <p className="m-0 text-muted">Không có widget phù hợp.</p>}
        {groups.map(([g, ws]) => (
          <section key={g} aria-label={g}>
            <h3 className="m-0 mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">{g}</h3>
            <ul className="m-0 p-0 list-none grid gap-1.5">
              {ws.map((w) => (
                <li key={w.id}>
                  <button type="button" onClick={() => { onAdd(w.id); onClose(); }}
                    className="w-full flex items-center gap-3 text-left rounded-md border border-line bg-panel2 hover:border-accent px-3 py-2 cursor-pointer text-fg">
                    <w.icon size={18} className="text-muted shrink-0" aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <b className="block text-[13px]">{w.title}</b>
                      {w.desc && <span className="block text-[11.5px] text-muted leading-snug">{w.desc}</span>}
                    </span>
                    <Plus size={15} className="text-accent shrink-0" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </Dialog>
  );
}
