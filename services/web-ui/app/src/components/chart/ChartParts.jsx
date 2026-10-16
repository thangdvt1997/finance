// Các mảnh giao diện nhỏ của biểu đồ: thanh Replay, hộp tạo cảnh báo giá (CHỈ cảnh báo), chọn mã.
import { useEffect, useMemo, useState } from "react";
import { Bell, Pause, Play, SkipBack, StepBack, StepForward, X } from "lucide-react";
import { Dialog } from "../dialog";
import { cn } from "../ui";
import { symbolLabel } from "../../lib/format";

export const REPLAY_SPEEDS = [1, 2, 5, 10, 25];

/** Thanh điều khiển phát lại: bước từng nến, phát/dừng, tốc độ (nến/giây), tua (thanh trượt), thoát. */
export function ReplayBar({ rp, total, headIdx, onStep, onPlay, onSpeed, onSeek, onExit, onRestart, headTime }) {
  if (!rp.on) return null;
  return (
    <div className="absolute bottom-2 left-1/2 z-30 flex w-[min(640px,calc(100%-1rem))] -translate-x-1/2 flex-wrap items-center gap-1.5 rounded-lg border border-line2 bg-panel/95 px-2 py-1.5 shadow-xl backdrop-blur" role="toolbar" aria-label="Replay" data-pc-ui>
      {rp.pick ? (
        <>
          <span className="text-[12px] font-medium text-accent">Bấm vào một nến để chọn điểm bắt đầu replay</span>
          <button type="button" className="btn !h-7 ml-auto" onClick={() => onSeek(Math.max(0, total - 1 - Math.min(200, Math.floor(total / 3))), true)}>~200 nến trước</button>
          <button type="button" className="btn !h-7" onClick={onExit}>Huỷ (Esc)</button>
        </>
      ) : (
        <>
          <button type="button" className="pc-ibtn" aria-label="Về điểm bắt đầu" title="Về điểm bắt đầu" onClick={onRestart}><SkipBack size={15} /></button>
          <button type="button" className="pc-ibtn" aria-label="Lùi 1 nến" title="Lùi 1 nến (←)" onClick={() => onStep(-1)}><StepBack size={15} /></button>
          <button type="button" className="pc-ibtn !h-8 !w-8 !bg-[var(--accent-bg)] !text-accent" aria-label={rp.playing ? "Tạm dừng" : "Phát"} title="Phát / dừng (Space)" onClick={onPlay}>{rp.playing ? <Pause size={16} /> : <Play size={16} />}</button>
          <button type="button" className="pc-ibtn" aria-label="Tiến 1 nến" title="Tiến 1 nến (→)" onClick={() => onStep(1)}><StepForward size={15} /></button>
          <label className="flex items-center gap-1 text-[11.5px] text-muted">Tốc độ
            <select className="field !h-7 !px-1" value={rp.speed} onChange={(e) => onSpeed(Number(e.target.value))} aria-label="Tốc độ phát lại">
              {REPLAY_SPEEDS.map((s) => <option key={s} value={s}>{s} nến/giây</option>)}
            </select>
          </label>
          <input type="range" className="mx-1 min-w-[90px] flex-1 accent-[var(--accent)]" min={0} max={Math.max(0, total - 1)} value={headIdx} aria-label="Tua replay" onChange={(e) => onSeek(Number(e.target.value))} />
          <span className="num text-[11.5px] text-muted">{headIdx + 1}/{total}</span>
          {headTime && <span className="num hidden text-[11px] text-faint sm:inline">{headTime}</span>}
          <button type="button" className="btn !h-7" onClick={onExit} aria-label="Thoát replay"><X size={13} /> Thoát</button>
        </>
      )}
    </div>
  );
}

/** Hộp xác nhận tạo cảnh báo giá tại mức vừa chọn. Không có đặt lệnh. */
export function AlertPopover({ symbol, price, last, dec, busy, error, onCreate, onCancel }) {
  const [name, setName] = useState("");
  const [ntfy, setNtfy] = useState(true);
  const [log, setLog] = useState(true);
  const [mode, setMode] = useState("once");
  const up = last != null ? price >= last : true;
  const op = up ? "gte" : "lte";
  const pTxt = Number(price).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
  useEffect(() => { setName(""); }, [price]);
  return (
    <form className="absolute right-3 top-12 z-40 w-[280px] rounded-lg border border-line2 bg-panel p-3 shadow-xl" data-pc-ui aria-label="Tạo cảnh báo giá"
      onSubmit={(e) => { e.preventDefault(); onCreate({ name: name.trim() || `${symbolLabel(symbol)} ${up ? "≥" : "≤"} ${pTxt}`, op, price, channels: [ntfy && "ntfy", log && "log"].filter(Boolean), mode }); }}>
      <div className="mb-2 flex items-center gap-2"><Bell size={15} className="text-accent" /><b className="text-[13px]">Cảnh báo giá {symbolLabel(symbol)}</b>
        <button type="button" className="pc-ibtn ml-auto" aria-label="Đóng" onClick={onCancel}><X size={14} /></button></div>
      <p className="m-0 mb-2 text-[12.5px]">Báo khi giá <b>{up ? "chạm / vượt lên" : "chạm / xuống dưới"}</b> <b className="num">{pTxt}</b></p>
      <input className="field mb-2 w-full" placeholder="Tên (tuỳ chọn)" aria-label="Tên cảnh báo" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
        <label className="flex items-center gap-1"><input type="checkbox" checked={ntfy} onChange={(e) => setNtfy(e.target.checked)} /> Điện thoại (ntfy)</label>
        <label className="flex items-center gap-1"><input type="checkbox" checked={log} onChange={(e) => setLog(e.target.checked)} /> Nhật ký</label>
        <select className="field !h-7" aria-label="Chế độ" value={mode} onChange={(e) => setMode(e.target.value)}><option value="once">Một lần</option><option value="repeat">Lặp lại (chờ 60 phút)</option></select>
      </div>
      {error && <p className="m-0 mb-2 text-[12px] text-down" role="alert">{error}</p>}
      <div className="flex items-center gap-2">
        <button type="submit" className="btn !border-[var(--accent)] text-accent" disabled={busy || (!ntfy && !log)}>{busy ? "Đang tạo…" : "Tạo cảnh báo"}</button>
        <button type="button" className="btn" onClick={onCancel}>Huỷ</button>
      </div>
      <p className="m-0 mt-2 text-[11px] text-faint">Chỉ gửi thông báo khi chạm mức giá. Không đặt lệnh.</p>
    </form>
  );
}

/** Hộp chọn mã (tìm theo mã/tên). */
export function SymbolPicker({ open, onClose, symbols, onPick, title = "Chọn mã" }) {
  const [q, setQ] = useState("");
  useEffect(() => { if (open) setQ(""); }, [open]);
  const list = useMemo(() => {
    const f = q.trim().toLowerCase();
    const all = symbols || [];
    const out = !f ? all : all.filter((s) => s.symbol.toLowerCase().includes(f) || (s.name || "").toLowerCase().includes(f));
    return out.slice(0, 120);
  }, [q, symbols]);
  return (
    <Dialog open={open} onClose={onClose} title={title}>
      <div className="p-3">
        <input data-autofocus className="field mb-2 w-full" placeholder="Tìm mã hoặc tên: EURUSD, vàng, VN:FPT…" aria-label="Tìm mã" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && list[0]) { e.preventDefault(); e.stopPropagation(); onPick(list[0].symbol); onClose(); } }} />
        <ul className="m-0 grid max-h-[50dvh] list-none gap-0.5 overflow-y-auto p-0">
          {list.map((s) => (
            <li key={s.symbol}>
              <button type="button" className="flex w-full cursor-pointer items-center gap-2 rounded border-0 bg-transparent px-2 py-1.5 text-left font-[inherit] text-fg hover:bg-panel2" onClick={() => { onPick(s.symbol); onClose(); }}>
                <b className="w-28 shrink-0 truncate text-[13px]">{symbolLabel(s.symbol)}</b><span className="truncate text-[12px] text-muted">{s.name || ""}</span>
              </button>
            </li>
          ))}
          {!list.length && <li className="p-3 text-center text-muted">Không có mã phù hợp.</li>}
        </ul>
      </div>
    </Dialog>
  );
}
