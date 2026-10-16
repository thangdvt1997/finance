// Hộp thoại thao tác: tạm hoãn (có mốc nhanh + tuỳ chọn) và đóng sự cố (kèm ghi chú nếu đóng một sự cố).
import { useId, useMemo, useState } from "react";
import { BellOff, CheckCheck } from "lucide-react";
import { Dialog } from "../../dialog";
import { ErrLine, Field, PRIMARY } from "../bits";
import { SNOOZE_MAX, SNOOZE_MIN, UNITS, clampSnooze, durVN, minutesToMorning, morningLabel } from "./model";

/** onPick(minutes) -> Promise<{ok,error}>. count > 1 = áp dụng cho nhiều sự cố. */
export function SnoozeDialog({ open, count = 1, onClose, onPick, busy }) {
  const [unit, setUnit] = useState("h");
  const [val, setVal] = useState("2");
  const [err, setErr] = useState(null);
  const id = useId();
  const k = UNITS.find((u) => u.id === unit).k;
  const custom = Number(val) * k;
  const customOk = Number.isFinite(custom) && custom >= SNOOZE_MIN && custom <= SNOOZE_MAX && Number.isInteger(Number(val));
  const morning = useMemo(() => (open ? { m: minutesToMorning(), t: morningLabel() } : null), [open]);
  const go = async (m) => { setErr(null); const r = await onPick(clampSnooze(m)); if (r?.ok) onClose(); else if (r?.error) setErr(r.error); };
  const presets = [
    { label: "1 giờ", m: 60 }, { label: "4 giờ", m: 240 },
    { label: "Đến sáng mai 08:00", m: morning?.m, sub: morning?.t },
  ];
  return (
    <Dialog open={open} onClose={onClose} title={count > 1 ? `Tạm hoãn ${count} sự cố` : "Tạm hoãn sự cố"} className="!max-w-[460px]"
      description="Sự cố được ẩn khỏi mục “Mới” cho đến hết thời gian; hết hạn sẽ tự quay về “Mới” nếu điều kiện còn. Giờ Việt Nam (UTC+7).">
      <div className="p-3 grid gap-3">
        <div className="grid gap-2" role="group" aria-label="Mốc nhanh">
          {presets.map((p) => (
            <button key={p.label} type="button" className="btn !h-auto !justify-between !py-2" disabled={busy} onClick={() => go(p.m)}>
              <span className="inline-flex items-center gap-2"><BellOff size={13} aria-hidden="true" />{p.label}</span>
              {p.sub && <span className="text-muted text-[11.5px]">{p.sub}</span>}
            </button>
          ))}
        </div>
        <form className="grid gap-2" onSubmit={(e) => { e.preventDefault(); if (customOk) go(custom); }}>
          <div className="fl-field">
            <label htmlFor={`${id}-v`} className="fl-lab">Tuỳ chọn</label>
            <div className="flex gap-2">
              <input id={`${id}-v`} className="field num !w-24" type="number" min="1" step="1" inputMode="numeric" value={val} onChange={(e) => setVal(e.target.value)} aria-describedby={`${id}-h`} />
              <select className="field" aria-label="Đơn vị" value={unit} onChange={(e) => setUnit(e.target.value)}>{UNITS.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}</select>
              <button type="submit" className={`btn ${PRIMARY}`} disabled={busy || !customOk}>Tạm hoãn</button>
            </div>
            <span id={`${id}-h`} className={customOk ? "fl-help" : "fl-err"}>{customOk ? `= ${durVN(custom)}` : `Nhập từ ${SNOOZE_MIN} phút đến 7 ngày (${SNOOZE_MAX.toLocaleString("vi-VN")} phút).`}</span>
          </div>
        </form>
        <ErrLine error={err} />
      </div>
    </Dialog>
  );
}

/** onConfirm(note) -> Promise<{ok,error}>. Đóng nhiều sự cố thì không có ô ghi chú (API hàng loạt không nhận ghi chú). */
export function ResolveDialog({ open, count = 1, title, onClose, onConfirm, busy }) {
  const [note, setNote] = useState("");
  const [err, setErr] = useState(null);
  const id = useId();
  const submit = async (e) => {
    e.preventDefault(); setErr(null);
    const r = await onConfirm(note.trim());
    if (r?.ok) { setNote(""); onClose(); } else if (r?.error) setErr(r.error);
  };
  return (
    <Dialog open={open} onClose={onClose} title={count > 1 ? `Đóng ${count} sự cố` : "Đóng sự cố"} className="!max-w-[460px]"
      description={count > 1 ? "Các sự cố sẽ chuyển sang “Đã đóng”. Nếu điều kiện còn tồn tại, hệ thống có thể mở lại ở lần đánh giá kế tiếp." : title}>
      <form className="p-3 grid gap-3" onSubmit={submit}>
        {count <= 1 && (
          <Field label="Ghi chú đóng (tuỳ chọn)" htmlFor={`${id}-n`} help={`${note.length}/1000 ký tự`}>
            <textarea id={`${id}-n`} className="field" maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Nguyên nhân / cách xử lý…" data-autofocus />
          </Field>
        )}
        <ErrLine error={err} />
        <div className="flex flex-wrap gap-2 justify-end">
          <button type="button" className="btn" onClick={onClose}>Huỷ</button>
          <button type="submit" className={`btn ${PRIMARY}`} disabled={busy}><CheckCheck size={14} aria-hidden="true" />{busy ? "Đang đóng…" : count > 1 ? `Đóng ${count} sự cố` : "Đóng sự cố"}</button>
        </div>
      </form>
    </Dialog>
  );
}
