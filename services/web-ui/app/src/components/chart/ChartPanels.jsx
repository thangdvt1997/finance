// Các tab của bảng cấu hình biểu đồ: Hiển thị (loại biểu đồ, màu nến, lưới, phiên, lịch/tin, so sánh), Đối tượng (cây hình vẽ + chỉ báo),
// Mẫu (lưu/áp/xoá/nhập/xuất JSON theo người dùng).
import { useRef, useState } from "react";
import { Check, Download, Eye, EyeOff, Lock, LockOpen, Pencil, Trash2, Upload } from "lucide-react";
import { cn } from "../ui";
import { CHART_TYPES, isDerived } from "./charttypes";
import { SESSIONS } from "./overlays";
import { TOOLS } from "./drawings";
import { IND } from "./indicators";
import { sanitizeTemplate } from "./chartPrefs";
import { symbolLabel } from "../../lib/format";

const NBARS = [500, 1500, 3000, 5000];
const Row = ({ children, label }) => <div className="grid gap-1 text-[12px] text-muted">{label && <span>{label}</span>}{children}</div>;
const Chk = ({ checked, onChange, children, disabled }) => <label className={cn("flex cursor-pointer items-center gap-2 text-[12.5px] text-fg", disabled && "opacity-50")}><input type="checkbox" checked={!!checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} /> {children}</label>;
const H = ({ children }) => <h3 className="m-0 mt-1 text-[11.5px] font-semibold uppercase tracking-wide text-faint">{children}</h3>;

export function ViewTab({ cfg, patchCfg, symbols, cmp, setCmp, symbol }) {
  const st = cfg.style || {};
  const setStyle = (p) => patchCfg((c) => ({ ...c, style: { ...(c.style || {}), ...p } }));
  const ses = cfg.sessions || { on: false, ids: ["tokyo", "london", "newyork"], lines: true };
  const setSes = (p) => patchCfg((c) => ({ ...c, sessions: { ...ses, ...p } }));
  const groups = [...new Set(CHART_TYPES.map((t) => t.group))];
  return (
    <div className="grid gap-3">
      <Row label="Loại biểu đồ">
        <select className="field" aria-label="Loại biểu đồ" value={cfg.type} onChange={(e) => patchCfg((c) => ({ ...c, type: e.target.value }))}>
          {groups.map((g) => <optgroup key={g} label={g}>{CHART_TYPES.filter((t) => t.group === g).map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</optgroup>)}
        </select>
      </Row>
      {isDerived(cfg.type) && (
        <Row label={cfg.type === "linebreak" ? "Số đường đảo chiều: 3" : "Kích thước gạch/hộp (0 = tự động theo ATR)"}>
          {cfg.type !== "linebreak" && <input type="number" min={0} step="any" className="field num" value={cfg.boxSize || 0} aria-label="Kích thước gạch" onChange={(e) => patchCfg((c) => ({ ...c, boxSize: Math.max(0, Number(e.target.value) || 0) }))} />}
          <span className="rounded border border-line bg-panel2 p-2 text-[11px] text-faint">Loại không theo thời gian được tính trên trình duyệt từ OHLC của nến (không có từng tick), thứ tự cao/thấp trong nến là giả định → xấp xỉ.</span>
        </Row>
      )}

      <H>Giao diện</H>
      <div className="flex flex-wrap items-center gap-3 text-[12px] text-muted">
        <label className="flex items-center gap-1.5">Nến tăng <input type="color" className="h-6 w-8 cursor-pointer rounded border border-line2 bg-transparent p-0" value={st.up || "#2bd08f"} onChange={(e) => setStyle({ up: e.target.value })} /></label>
        <label className="flex items-center gap-1.5">Nến giảm <input type="color" className="h-6 w-8 cursor-pointer rounded border border-line2 bg-transparent p-0" value={st.down || "#ff5c7a"} onChange={(e) => setStyle({ down: e.target.value })} /></label>
        <button type="button" className="btn !h-7" onClick={() => setStyle({ up: undefined, down: undefined })}>Mặc định</button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Row label="Lưới"><select className="field" aria-label="Lưới" value={st.grid || "both"} onChange={(e) => setStyle({ grid: e.target.value })}><option value="both">Ngang + dọc</option><option value="h">Chỉ ngang</option><option value="v">Chỉ dọc</option><option value="none">Không</option></select></Row>
        <Row label="Thang giá"><select className="field" aria-label="Phía thang giá" value={st.scaleSide || "right"} onChange={(e) => setStyle({ scaleSide: e.target.value })}><option value="right">Bên phải</option><option value="left">Bên trái</option></select></Row>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        <Chk checked={cfg.log} onChange={(v) => patchCfg((c) => ({ ...c, log: v, pct: v ? false : c.pct }))}>Thang logarit (L)</Chk>
        <Chk checked={cfg.pct} onChange={(v) => patchCfg((c) => ({ ...c, pct: v, log: v ? false : c.log }))}>Thang phần trăm (%)</Chk>
        <Chk checked={cfg.auto !== false} onChange={(v) => patchCfg((c) => ({ ...c, auto: v }))}>Tự co giãn trục giá</Chk>
        <Chk checked={cfg.volume !== false} onChange={(v) => patchCfg((c) => ({ ...c, volume: v }))}>Khối lượng</Chk>
      </div>

      <H>Phiên giao dịch & mốc giá</H>
      <Chk checked={ses.on} onChange={(v) => setSes({ on: v })}>Tô vùng phiên (khung ≤ H4)</Chk>
      {ses.on && (
        <div className="ml-5 grid gap-1.5">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {SESSIONS.map((s) => (
              <label key={s.id} className="flex cursor-pointer items-center gap-1.5 text-[12.5px]"><input type="checkbox" checked={ses.ids.includes(s.id)} onChange={(e) => setSes({ ids: e.target.checked ? [...ses.ids, s.id] : ses.ids.filter((x) => x !== s.id) })} />
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />{s.label}</label>
            ))}
          </div>
          <Chk checked={ses.lines !== false} onChange={(v) => setSes({ lines: v })}>Đường mở (liền) / đóng (chấm) phiên</Chk>
        </div>
      )}
      <Chk checked={cfg.prevClose} onChange={(v) => patchCfg((c) => ({ ...c, prevClose: v }))}>Đường giá đóng cửa trước</Chk>
      <Chk checked={cfg.dayOpen} onChange={(v) => patchCfg((c) => ({ ...c, dayOpen: v }))}>Đường giá mở cửa ngày</Chk>

      <H>Sự kiện & cảnh báo</H>
      <Chk checked={cfg.events} onChange={(v) => patchCfg((c) => ({ ...c, events: v }))}>Sự kiện lịch kinh tế tác động CAO</Chk>
      {cfg.events && <div className="ml-5"><Chk checked={cfg.eventsAll} onChange={(v) => patchCfg((c) => ({ ...c, eventsAll: v }))}>Hiện cả sự kiện không liên quan tới mã</Chk></div>}
      <Chk checked={cfg.news} onChange={(v) => patchCfg((c) => ({ ...c, news: v }))}>Tin quan trọng (sắc thái mạnh) của mã</Chk>
      <Chk checked={cfg.alerts !== false} onChange={(v) => patchCfg((c) => ({ ...c, alerts: v }))}>Hiện đường cảnh báo giá của tôi (kéo để đổi mức)</Chk>

      <H>So sánh / Spread / Tỉ lệ</H>
      <Row>
        <select className="field" aria-label="Mã so sánh" value={cmp?.symbol || ""} onChange={(e) => setCmp(e.target.value ? { symbol: e.target.value, mode: cmp?.mode || "pct" } : null)}>
          <option value="">— Không —</option>
          {(symbols || []).filter((s) => s.symbol !== symbol).map((s) => <option key={s.symbol} value={s.symbol}>{symbolLabel(s.symbol)}{s.name ? ` · ${s.name}` : ""}</option>)}
        </select>
      </Row>
      {cmp?.symbol && (
        <div className="grid gap-1.5">
          <div className="seg" role="group" aria-label="Kiểu so sánh">
            {[["pct", "Chồng % "], ["spread", "Spread A−B"], ["ratio", "Tỉ lệ A/B"]].map(([v, l]) => <button key={v} type="button" aria-pressed={(cmp.mode || "pct") === v} onClick={() => setCmp({ ...cmp, mode: v })}>{l}</button>)}
          </div>
          <Chk checked={cfg.corr} onChange={(v) => patchCfg((c) => ({ ...c, corr: v }))}>Pane tương quan (cửa sổ {cfg.corrWin || 50} nến) dưới biểu đồ</Chk>
          <p className="m-0 text-[11px] text-faint">Spread/tỉ lệ tính từ nến hai mã khớp theo thời gian (nến tổng hợp xấp xỉ: high = A.high ∓ B.low…). Tương quan = Pearson lăn của lợi suất log.</p>
        </div>
      )}

      <Row label="Số nến nạp ban đầu (kéo sang trái để tải thêm tới 20.000)">
        <select className="field" aria-label="Số nến nạp" value={cfg.nBars} onChange={(e) => patchCfg((c) => ({ ...c, nBars: Number(e.target.value) }))}>{NBARS.map((n) => <option key={n} value={n}>{n.toLocaleString("en-US")} nến</option>)}</select>
      </Row>
    </div>
  );
}

export function ObjectsTab({ drawings, dapi, indicators, setIndicators, activeId }) {
  const [editId, setEditId] = useState(null);
  const [text, setText] = useState("");
  const label = (d) => d.name || TOOLS.find((t) => t.id === d.type)?.label || d.type;
  const commit = (id) => { if (text.trim()) dapi?.patch(id, { name: text.trim().slice(0, 120) }); setEditId(null); };
  return (
    <div className="grid gap-3">
      <div>
        <H>Hình vẽ ({drawings.length})</H>
        {!drawings.length && <p className="m-0 mt-1 text-[12px] text-muted">Chưa có hình vẽ nào ở mã/khung này.</p>}
        <ul className="m-0 mt-1 list-none space-y-0.5 p-0">
          {drawings.map((d) => (
            <li key={d.id} className={cn("flex items-center gap-1 rounded-md border border-line bg-panel2 px-1 py-0.5", d.id === activeId && "!border-[var(--accent)]", d.hidden && "opacity-60")}>
              <button type="button" className="pc-ibtn" aria-label={d.hidden ? "Hiện" : "Ẩn"} onClick={() => dapi.patch(d.id, { hidden: !d.hidden })}>{d.hidden ? <EyeOff size={14} /> : <Eye size={14} />}</button>
              <button type="button" className={cn("pc-ibtn", d.locked && "!text-accent")} aria-label={d.locked ? "Mở khoá" : "Khoá"} aria-pressed={!!d.locked} onClick={() => dapi.patch(d.id, { locked: !d.locked })}>{d.locked ? <Lock size={14} /> : <LockOpen size={14} />}</button>
              <input type="color" aria-label="Màu" className="h-5 w-6 shrink-0 cursor-pointer rounded border border-line2 bg-transparent p-0" value={/^#[0-9a-f]{6}$/i.test(d.style?.color || "") ? d.style.color : "#5aa9ff"} onChange={(e) => dapi.patch(d.id, { color: e.target.value }, true)} />
              {editId === d.id ? (
                <input autoFocus className="field !h-7 min-w-0 flex-1" aria-label="Tên hình vẽ" value={text} maxLength={120} onChange={(e) => setText(e.target.value)} onBlur={() => commit(d.id)}
                  onKeyDown={(e) => { if (e.key === "Enter") commit(d.id); else if (e.key === "Escape") { e.stopPropagation(); setEditId(null); } }} />
              ) : (
                <button type="button" className="min-w-0 flex-1 cursor-pointer truncate border-0 bg-transparent p-0 text-left font-[inherit] text-[12.5px] text-fg" onClick={() => dapi.select(d.id)} onDoubleClick={() => { setEditId(d.id); setText(label(d)); }} title="Bấm để chọn, bấm đúp để đổi tên">{label(d)}</button>
              )}
              <button type="button" className="pc-ibtn" aria-label="Đổi tên" onClick={() => { setEditId(d.id); setText(label(d)); }}><Pencil size={13} /></button>
              <button type="button" className="pc-ibtn text-down" aria-label="Xoá" disabled={d.locked} onClick={() => dapi.remove(d.id)}><Trash2 size={14} /></button>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <H>Chỉ báo ({indicators.length})</H>
        <ul className="m-0 mt-1 list-none space-y-0.5 p-0">
          {indicators.map((x) => (
            <li key={x.id} className={cn("flex items-center gap-1 rounded-md border border-line bg-panel2 px-1 py-0.5", !x.visible && "opacity-60")}>
              <button type="button" className="pc-ibtn" aria-label={x.visible ? "Ẩn" : "Hiện"} onClick={() => setIndicators((l) => l.map((y) => (y.id === x.id ? { ...y, visible: !y.visible } : y)))}>{x.visible ? <Eye size={14} /> : <EyeOff size={14} />}</button>
              <input type="color" aria-label="Màu" className="h-5 w-6 shrink-0 cursor-pointer rounded border border-line2 bg-transparent p-0" value={Object.values(x.colors || {})[0] || "#f0b84f"}
                onChange={(e) => setIndicators((l) => l.map((y) => (y.id === x.id ? { ...y, colors: { ...y.colors, [Object.keys(y.colors)[0]]: e.target.value } } : y)))} />
              <span className="min-w-0 flex-1 truncate text-[12.5px]">{IND[x.type]?.name || x.type} <span className="text-faint">{(IND[x.type]?.params || []).map((p) => x.params[p.k]).join(", ")}</span></span>
              <button type="button" className="pc-ibtn text-down" aria-label="Gỡ" onClick={() => setIndicators((l) => l.filter((y) => y.id !== x.id))}><Trash2 size={14} /></button>
            </li>
          ))}
          {!indicators.length && <li className="text-[12px] text-muted">Chưa có chỉ báo.</li>}
        </ul>
      </div>
    </div>
  );
}

export function TemplatesTab({ templates, onSave, onApply, onDelete, onImport, serverOk, status }) {
  const [name, setName] = useState("");
  const [withWs, setWithWs] = useState(false);
  const [json, setJson] = useState("");
  const [msg, setMsg] = useState("");
  const fileRef = useRef(null);
  const flash = (m) => { setMsg(m); setTimeout(() => setMsg(""), 4000); };
  const exportOne = async (t, download) => {
    const { remote, ...clean } = t; // eslint-disable-line no-unused-vars
    const text = JSON.stringify(clean, null, 2);
    if (download) {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([text], { type: "application/json" })); a.download = `mau-bieu-do-${t.name.replace(/[^\w-]+/g, "_")}.json`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 3000);
    } else { try { await navigator.clipboard.writeText(text); flash("Đã sao chép JSON."); } catch { setJson(text); flash("Không ghi được clipboard: JSON hiện ở ô bên dưới."); } }
  };
  const doImport = (text) => {
    try {
      const o = JSON.parse(text);
      const list = Array.isArray(o) ? o : [o];
      let n = 0;
      for (const it of list) { const t = sanitizeTemplate(it); if (t) { onImport(t); n++; } }
      flash(n ? `Đã nhập ${n} mẫu.` : "JSON không có mẫu hợp lệ.");
      if (n) setJson("");
    } catch { flash("JSON không hợp lệ."); }
  };
  return (
    <div className="grid gap-3">
      <p className="m-0 rounded border border-line bg-panel2 p-2 text-[11.5px] text-muted">
        Mẫu gồm chỉ báo + loại biểu đồ + giao diện/lớp phủ của ô đang chọn (tuỳ chọn: cả bố cục nhiều biểu đồ). Lưu ở <b>{serverOk ? "tài khoản (máy chủ)" : "trình duyệt này (máy chủ chưa sẵn sàng)"}</b>
        {serverOk ? ", đồng thời giữ bản sao trong trình duyệt" : ""}. {status === "saving" && "Đang lưu…"}{status === "error" && " Lưu máy chủ lỗi: đã giữ bản cục bộ."}
      </p>
      <form className="grid gap-1.5" onSubmit={(e) => { e.preventDefault(); if (name.trim()) { onSave(name.trim(), withWs); setName(""); } }}>
        <div className="flex gap-1.5"><input className="field min-w-0 flex-1" placeholder="Tên mẫu mới…" aria-label="Tên mẫu" maxLength={40} value={name} onChange={(e) => setName(e.target.value)} /><button type="submit" className="btn" disabled={!name.trim()}><Check size={14} /> Lưu mẫu</button></div>
        <Chk checked={withWs} onChange={setWithWs}>Kèm bố cục nhiều biểu đồ (mã/khung từng ô)</Chk>
      </form>
      <H>Mẫu của tôi ({templates.length})</H>
      <ul className="m-0 list-none space-y-1 p-0">
        {templates.map((t) => (
          <li key={t.name} className="flex flex-wrap items-center gap-1 rounded-md border border-line bg-panel2 px-2 py-1.5">
            <b className="min-w-0 flex-1 truncate text-[12.5px]" title={t.name}>{t.name}</b>
            <span className="chip" title={t.remote ? "Đã lưu trên máy chủ" : "Chỉ trong trình duyệt này"}>{t.remote ? "máy chủ" : "cục bộ"}</span>
            {t.ws && <span className="chip">bố cục</span>}
            <button type="button" className="btn !h-7" onClick={() => onApply(t)}>Áp dụng</button>
            <button type="button" className="pc-ibtn" aria-label="Sao chép JSON" title="Sao chép JSON" onClick={() => exportOne(t, false)}><Upload size={14} /></button>
            <button type="button" className="pc-ibtn" aria-label="Tải về .json" title="Tải về .json" onClick={() => exportOne(t, true)}><Download size={14} /></button>
            <button type="button" className="pc-ibtn text-down" aria-label={`Xoá mẫu ${t.name}`} onClick={() => onDelete(t.name)}><Trash2 size={14} /></button>
          </li>
        ))}
        {!templates.length && <li className="text-[12px] text-muted">Chưa có mẫu. Cấu hình biểu đồ rồi đặt tên và bấm "Lưu mẫu".</li>}
      </ul>
      <H>Nhập mẫu (dán JSON hoặc chọn tệp)</H>
      <textarea className="field min-h-[72px] w-full font-mono text-[11px]" aria-label="JSON mẫu" placeholder='{"name":"Của tôi","cfg":{...},"ind":[...]}' value={json} onChange={(e) => setJson(e.target.value)} />
      <div className="flex gap-1.5">
        <button type="button" className="btn" disabled={!json.trim()} onClick={() => doImport(json)}>Nhập</button>
        <button type="button" className="btn" onClick={() => fileRef.current?.click()}>Chọn tệp .json</button>
        <input ref={fileRef} type="file" accept="application/json,.json" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f && f.size < 200_000) doImport(await f.text()); }} />
      </div>
      {msg && <p className="m-0 text-[12px] text-accent" role="status">{msg}</p>}
    </div>
  );
}
