// Bảng cấu hình biểu đồ: thêm/bớt/chỉnh chỉ báo (tham số, màu, thứ tự pane), tín hiệu, hiển thị (log, so sánh, số nến).
// Mọi thay đổi do trang cha lưu vào localStorage nên lần sau mở lại vẫn giữ nguyên.
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Eye, EyeOff, Plus, Search, Trash2, X } from "lucide-react";
import { cn } from "../ui";
import { IND, IND_ORDER, defaultColors, defaultParams } from "./indicators";
import { SIGNAL_KINDS } from "./signals";
import { t } from "../../lib/i18n";
import { numLocale } from "../../lib/format";

const uid = () => Math.random().toString(36).slice(2, 8);
const MA_PERIODS = [20, 50, 100, 200, 10, 30, 9, 21, 55];

export function makeIndicator(type, existing = []) {
  const params = defaultParams(type);
  if (["sma", "ema", "wma"].includes(type)) {
    const used = new Set(existing.filter((x) => x.type === type).map((x) => x.params.period));
    params.period = MA_PERIODS.find((p) => !used.has(p)) || params.period;
  }
  return { id: uid(), type, params, colors: defaultColors(type, existing.length), visible: true, width: 1.5 };
}
export const DEFAULT_INDICATORS = () => {
  const a = makeIndicator("ema", []);
  a.params.period = 20;
  const b = makeIndicator("ema", [a]);
  b.params.period = 50;
  return [a, b];
};

export const NBARS = [500, 1500, 3000, 5000];

export default function IndicatorPanel({ open, onClose, tab, setTab, indicators, setIndicators, focusId, cfg, setCfg, symbols, compareSym, setCompareSym, nBars, setNBars }) {
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState(null);
  useEffect(() => { if (focusId) { setOpenId(focusId); setTab("ind"); } }, [focusId, setTab]);
  const list = useMemo(() => {
    const f = q.trim().toLowerCase();
    return IND_ORDER.filter((k) => !f || IND[k].name.toLowerCase().includes(f) || IND[k].desc.toLowerCase().includes(f) || k.includes(f));
  }, [q]);
  if (!open) return null;

  const upd = (id, patch) => setIndicators((l) => l.map((x) => (x.id === id ? { ...x, ...patch } : x)));
  const move = (id, d) => setIndicators((l) => {
    const i = l.findIndex((x) => x.id === id), j = i + d;
    if (i < 0 || j < 0 || j >= l.length) return l;
    const c = [...l]; [c[i], c[j]] = [c[j], c[i]]; return c;
  });
  const kinds = new Set(cfg.signals.kinds);

  return (
    <div className="mkt-pop" role="dialog" aria-label={t("Cấu hình biểu đồ")}>
      <div className="flex items-center gap-1 border-b border-line px-2 py-1.5">
        {[["ind", t("Các chỉ báo")], ["sig", t("Tín hiệu")], ["view", t("Hiển thị")]].map(([id, l]) => (
          <button key={id} type="button" aria-pressed={tab === id}
            className={cn("h-7 cursor-pointer rounded-md border-0 px-2.5 text-[12px] font-medium", tab === id ? "bg-accent text-[var(--accent-fg)]" : "bg-transparent text-muted hover:text-fg")}
            onClick={() => setTab(id)}>{l}</button>
        ))}
        <button type="button" aria-label={t("Đóng")} className="ml-auto grid h-7 w-7 cursor-pointer place-items-center rounded-md border-0 bg-transparent text-muted hover:text-fg" onClick={onClose}><X size={15} /></button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2.5">
        {tab === "ind" && (
          <>
            <h3 className="m-0 mb-1.5 text-[11.5px] font-semibold text-muted">{t("Đang dùng ({n})", { n: indicators.length })}</h3>
            {!indicators.length && <p className="m-0 mb-2 text-muted">{t("Chưa có chỉ báo. Thêm ở danh sách bên dưới.")}</p>}
            <ul className="m-0 mb-3 list-none space-y-1 p-0">
              {indicators.map((x, i) => {
                const def = IND[x.type];
                const op = openId === x.id;
                return (
                  <li key={x.id} className="rounded-md border border-line bg-panel2">
                    <div className="flex items-center gap-1 px-1.5 py-1">
                      <button type="button" aria-label={x.visible ? t("Ẩn") : t("Hiện")} className="pc-ibtn" onClick={() => upd(x.id, { visible: !x.visible })}>{x.visible ? <Eye size={14} /> : <EyeOff size={14} />}</button>
                      <button type="button" className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 border-0 bg-transparent p-0 text-left font-[inherit] text-fg" aria-expanded={op} onClick={() => setOpenId(op ? null : x.id)}>
                        <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: Object.values(x.colors)[0] }} />
                        <span className="truncate font-medium">{def.name}</span>
                        <span className="truncate text-faint">{def.params.map((p) => x.params[p.k]).join(", ")}</span>
                        <span className="ml-auto shrink-0 text-[10.5px] text-faint">{def.group === "pane" ? t("pane") : t("chồng")}</span>
                      </button>
                      <button type="button" aria-label={t("Lên")} className="pc-ibtn" disabled={i === 0} onClick={() => move(x.id, -1)}><ChevronUp size={14} /></button>
                      <button type="button" aria-label={t("Xuống")} className="pc-ibtn" disabled={i === indicators.length - 1} onClick={() => move(x.id, 1)}><ChevronDown size={14} /></button>
                      <button type="button" aria-label={t("Gỡ")} className="pc-ibtn text-down" onClick={() => setIndicators((l) => l.filter((y) => y.id !== x.id))}><Trash2 size={14} /></button>
                    </div>
                    {op && (
                      <div className="grid gap-2 border-t border-line px-2.5 py-2">
                        {def.params.length > 0 && (
                          <div className="grid grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))] gap-2">
                            {def.params.map((p) => (
                              <label key={p.k} className="grid gap-0.5 text-[11.5px] text-muted">{p.label}
                                <input type="number" className="field !h-8 num" value={x.params[p.k] ?? p.def} min={p.min} max={p.max} step={p.step}
                                  onChange={(e) => { const v = Number(e.target.value); if (Number.isFinite(v) && v >= p.min && v <= p.max) upd(x.id, { params: { ...x.params, [p.k]: v } }); }} />
                              </label>
                            ))}
                          </div>
                        )}
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                          {def.outputs.map((o) => (
                            <label key={o.key} className="flex items-center gap-1.5 text-[11.5px] text-muted">
                              <input type="color" className="h-6 w-7 cursor-pointer rounded border border-line2 bg-transparent p-0" value={x.colors[o.key] || "#f0b84f"}
                                onChange={(e) => upd(x.id, { colors: { ...x.colors, [o.key]: e.target.value } })} />
                              {o.label}
                            </label>
                          ))}
                          <label className="flex items-center gap-1.5 text-[11.5px] text-muted">{t("Độ dày")}
                            <select className="field !h-7 !px-1" value={x.width || 1.5} onChange={(e) => upd(x.id, { width: Number(e.target.value) })}>
                              <option value={1}>1</option><option value={1.5}>1.5</option><option value={2}>2</option><option value={3}>3</option>
                            </select>
                          </label>
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>

            <h3 className="m-0 mb-1.5 text-[11.5px] font-semibold text-muted">{t("Thêm chỉ báo")}</h3>
            <div className="relative mb-2">
              <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" />
              <input className="field w-full !pl-7" placeholder={t("Tìm: EMA, RSI, Ichimoku…")} aria-label={t("Tìm chỉ báo")} value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            {["overlay", "pane"].map((g) => {
              const items = list.filter((k) => IND[k].group === g);
              if (!items.length) return null;
              return (
                <div key={g} className="mb-2">
                  <div className="mb-1 text-[11px] uppercase tracking-wide text-faint">{g === "overlay" ? t("Chồng trên giá") : t("Pane riêng bên dưới")}</div>
                  <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(10.5rem,1fr))] gap-1 p-0">
                    {items.map((k) => (
                      <li key={k}>
                        <button type="button" className="flex w-full cursor-pointer items-center gap-1.5 rounded-md border border-line bg-panel px-2 py-1.5 text-left font-[inherit] text-fg hover:border-line2"
                          title={IND[k].desc} onClick={() => { const n = makeIndicator(k, indicators); setIndicators((l) => [...l, n]); setOpenId(n.id); }}>
                          <Plus size={13} className="shrink-0 text-accent" aria-hidden="true" />
                          <span className="min-w-0"><b className="block truncate text-[12.5px]">{IND[k].name}</b><span className="block truncate text-[10.5px] text-faint">{IND[k].desc}</span></span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
            <button type="button" className="btn mt-1" onClick={() => setIndicators(DEFAULT_INDICATORS())}>{t("Đặt lại mặc định (EMA 20 + 50)")}</button>
            <p className="m-0 mt-2 text-[11px] text-faint">{t("Cấu hình tự lưu trong trình duyệt này. Kéo đường phân cách giữa các pane để đổi chiều cao.")}</p>
          </>
        )}

        {tab === "sig" && (
          <>
            <label className="mb-3 flex cursor-pointer items-center gap-2 font-medium">
              <input type="checkbox" checked={cfg.signals.on} onChange={(e) => setCfg((c) => ({ ...c, signals: { ...c.signals, on: e.target.checked } }))} />
              {t("Hiện tín hiệu trên biểu đồ (mũi tên + nhãn)")}
            </label>
            <ul className="m-0 list-none space-y-1.5 p-0">
              {SIGNAL_KINDS.map((k) => (
                <li key={k.id}>
                  <label className="flex cursor-pointer items-center gap-2">
                    <input type="checkbox" checked={kinds.has(k.id)} disabled={!cfg.signals.on}
                      onChange={(e) => setCfg((c) => { const s = new Set(c.signals.kinds); if (e.target.checked) s.add(k.id); else s.delete(k.id); return { ...c, signals: { ...c.signals, kinds: [...s] } }; })} />
                    <span className="chip">{k.short}</span> {k.label}
                  </label>
                </li>
              ))}
            </ul>
            <p className="m-0 mt-3 rounded border border-line bg-panel2 p-2 text-[11px] text-muted">
              {t("Tín hiệu tính ngay trên trình duyệt từ nến đang hiển thị. Chỉ báo kỹ thuật, không phải khuyến nghị đầu tư; có thể có tín hiệu nhiễu ở thị trường đi ngang.")}
            </p>
          </>
        )}

        {tab === "view" && (
          <div className="grid gap-3">
            <label className="grid gap-1 text-[12px] text-muted">{t("So sánh với mã khác (chuyển sang thang % )")}
              <select className="field" value={compareSym || ""} onChange={(e) => setCompareSym(e.target.value || null)}>
                <option value="">{t("— Không so sánh —")}</option>
                {(symbols || []).map((s) => <option key={s.symbol} value={s.symbol}>{s.symbol.replace(/^[A-Za-z]+:/, "")}{s.name ? ` · ${s.name}` : ""}</option>)}
              </select>
            </label>
            <label className="grid gap-1 text-[12px] text-muted">{t("Số nến nạp")}
              <select className="field" value={nBars} onChange={(e) => setNBars(Number(e.target.value))}>
                {NBARS.map((n) => <option key={n} value={n}>{t("{n} nến", { n: n.toLocaleString(numLocale()) })}</option>)}
              </select>
            </label>
            {[["log", t("Thang giá logarit (L)")], ["auto", t("Tự động co giãn trục giá")], ["volume", t("Hiện khối lượng")]].map(([k, l]) => (
              <label key={k} className="flex cursor-pointer items-center gap-2">
                <input type="checkbox" checked={k === "log" ? !!cfg.log : cfg[k] !== false} onChange={(e) => setCfg((c) => ({ ...c, [k]: e.target.checked }))} /> {l}
              </label>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
