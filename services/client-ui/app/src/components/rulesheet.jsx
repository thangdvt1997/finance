// Form tạo/sửa quy tắc cảnh báo cá nhân (chạy trên máy chủ). Schema theo services/alert-rules/models.py (RuleIn) + scope.py (clientize):
// client chỉ dùng kênh app/push, cooldown >= 5 phút, điều kiện `account` bắt buộc gắn tài khoản của chính họ, tối đa 20 quy tắc.
import { useId, useState } from "react";
import { Eye, Plus, Trash2 } from "lucide-react";
import { Chip, Field, Notice, Sheet, cn } from "./ui";
import { accountTitle } from "../lib/auth";
import { apiWrite, detailText } from "../lib/api";
import { useQuotes, useSymbols } from "../lib/queries";
import { clean, price } from "../lib/format";
import { t } from "../lib/i18n";

export const MAX_RULES = 20;
export const MIN_COOLDOWN = 5;
const MAX_CONDS = 8;
const SYMBOL_RE = /^[A-Za-z0-9:._-]{1,32}$/;
const uid = () => Math.random().toString(36).slice(2, 9);

export const COND_TYPES = ["price", "pct_change", "indicator", "news_window", "account"];
export const condTypeLabel = (k) => (k === "price" ? t("Giá") : k === "pct_change" ? t("% biến động") : k === "indicator" ? t("Chỉ báo") : k === "news_window" ? t("Tin mạnh") : k === "account" ? t("Tài khoản") : k);
export const opLabel = (op) => (op === "gte" ? "≥" : op === "lte" ? "≤" : op === "cross_up" ? t("cắt lên trên") : op === "cross_down" ? t("cắt xuống dưới") : op === "abs_gte" ? t("biến động tuyệt đối ≥") : op);
const METRICS = ["margin_level", "equity_drawdown_24h", "floating_pl_pct"];
export const metricLabel = (m) => (m === "margin_level" ? t("Mức margin (%)") : m === "equity_drawdown_24h" ? t("Sụt vốn 24h từ đỉnh (%)") : m === "floating_pl_pct" ? t("Lãi/lỗ đang mở (% số dư)") : m);
const FIELDS = ["rsi", "adx", "stoch_k", "bb_pctb", "ema200_dist_pct", "atr_pct", "macd_hist", "heat", "bias"];
const fieldLabel = (f) => (f === "rsi" ? "RSI" : f === "adx" ? "ADX" : f === "stoch_k" ? "Stochastic %K" : f === "bb_pctb" ? "Bollinger %B" : f === "ema200_dist_pct" ? t("Cách EMA200 (%)") : f === "atr_pct" ? t("ATR (% giá)") : f === "macd_hist" ? "MACD histogram" : f === "heat" ? t("Độ nóng") : f === "bias" ? t("Thiên hướng") : f);
const TFS = ["M1", "M5", "M15", "H1", "H4", "D1"];
const WINDOWS = [5, 15, 30, 60, 240, 1440];
const winLabel = (m) => (m >= 1440 ? t("1 ngày") : m >= 60 ? t("{n} giờ", { n: m / 60 }) : t("{n} phút", { n: m }));

const sym = (s) => String(s || "").replace(/^(VN|US):/, "");

/** Tóm tắt một điều kiện bằng tiếng thường (dùng cho danh sách + tên tự động). */
export function summarizeCond(c) {
  switch (c.type) {
    case "account": return `${metricLabel(c.metric)} ${opLabel(c.op)} ${c.value}`;
    case "price": return t("Giá {s} {op} {v}", { s: sym(c.symbol), op: opLabel(c.op), v: c.value });
    case "pct_change": return t("{s} biến động {op} {v}% trong {w}", { s: sym(c.symbol), op: opLabel(c.op), v: c.value, w: winLabel(Number(c.window_min)) });
    case "news_window": return c.phase === "active" ? t("Tin tác động {i} đang diễn ra", { i: c.impact === "high" ? t("cao") : t("vừa") }) : t("Tin tác động {i} sắp ra trong {m} phút", { i: c.impact === "high" ? t("cao") : t("vừa"), m: c.within_min });
    case "indicator": return t("{f} {tf} {s} {op} {v}", { f: fieldLabel(c.field), tf: c.tf, s: sym(c.symbol), op: opLabel(c.op), v: c.value });
    case "state": return t("{s} {tf}: {f} = {v}", { s: sym(c.symbol), tf: c.tf, f: c.field, v: c.is });
    case "sentiment": return t("Tâm lý tin {s}: {op} {v}", { s: sym(c.symbol), op: opLabel(c.op), v: c.value });
    default: return String(c.type);
  }
}

// ---- trạng thái form <-> payload ----
const blank = (type, o = {}) => {
  const b = { _k: uid(), type, symbol: o.symbol || "EURUSD", op: "gte", value: "", window_min: "60", tf: "H1", field: "rsi", impact: "high", within_min: "30", phase: "upcoming", country: "", account_id: o.account_id || "", metric: "margin_level" };
  if (type === "account") { b.metric = o.metric || "margin_level"; b.op = "lte"; b.value = o.value ?? "300"; }
  if (type === "pct_change") b.op = "abs_gte";
  return b;
};
const fromCond = (c) => !COND_TYPES.includes(c.type) ? { _k: uid(), type: c.type, _orig: c } : ({ ...blank(c.type), ...Object.fromEntries(Object.entries(c).map(([k, v]) => [k === "is" ? "is_" : k, v == null ? "" : typeof v === "number" ? String(v) : v])), _k: uid(), type: c.type });
export const PRESETS = {
  price: (o) => ({ name: "", conds: [blank("price", o)], mode: "once" }),
  margin: (o) => ({ name: "", conds: [blank("account", { ...o, metric: "margin_level", value: "300" })], mode: "repeat", level: "crit" }),
  loss: (o) => ({ name: "", conds: [blank("account", { ...o, metric: "floating_pl_pct", value: "-3" })], mode: "repeat", level: "warn" }),
  drawdown: (o) => ({ name: "", conds: [{ ...blank("account", { ...o, metric: "equity_drawdown_24h", value: "5" }), op: "gte" }], mode: "repeat", level: "warn" }),
  news: () => ({ name: "", conds: [blank("news_window")], mode: "repeat", level: "info" }),
};

const num = (s) => { const x = String(s ?? "").trim().replace(",", "."); return x === "" || !/^-?\d+(\.\d+)?$/.test(x) ? NaN : Number(x); };
const intIn = (s, lo, hi) => { const n = num(s); return Number.isInteger(n) && n >= lo && n <= hi; };

/** Kiểm tra một điều kiện -> {field: lỗi}. */
function validateCond(c) {
  const e = {};
  const v = num(c.value);
  const needSym = c.type === "price" || c.type === "pct_change" || c.type === "indicator";
  if (needSym && !SYMBOL_RE.test(String(c.symbol || "").trim())) e.symbol = t("Mã không hợp lệ (chữ, số, : . _ -).");
  if (c.type === "price" || c.type === "pct_change" || c.type === "indicator" || c.type === "account") {
    if (Number.isNaN(v) || Math.abs(v) > 1e12) e.value = t("Nhập một con số.");
    else if (c.type === "account" && c.metric === "margin_level" && (v < 0 || v > 100000)) e.value = t("Nhập số từ {lo} đến {hi}.", { lo: 0, hi: 100000 });
    else if (c.type === "account" && c.metric === "equity_drawdown_24h" && (v < 0 || v > 100)) e.value = t("Nhập số từ {lo} đến {hi}.", { lo: 0, hi: 100 });
    else if (c.type === "account" && c.metric === "floating_pl_pct" && (v < -100 || v > 1000)) e.value = t("Nhập số từ {lo} đến {hi}.", { lo: -100, hi: 1000 });
  }
  if (c.type === "pct_change" && !intIn(c.window_min, 1, 1440)) e.window_min = t("Số phút từ 1 đến 1440.");
  if (c.type === "news_window") {
    if (!intIn(c.within_min, 5, 720)) e.within_min = t("Số phút từ 5 đến 720.");
    if (c.country && !/^[A-Za-z]{2,8}$/.test(c.country.trim())) e.country = t("Mã quốc gia 2-8 chữ cái.");
  }
  if (c.type === "account" && !c.account_id) e.account_id = t("Chọn tài khoản của bạn.");
  return e;
}

function toCond(c) {
  switch (c.type) {
    case "price": return { type: "price", symbol: c.symbol.trim().toUpperCase(), op: c.op, value: num(c.value) };
    case "pct_change": return { type: "pct_change", symbol: c.symbol.trim().toUpperCase(), window_min: Number(c.window_min), op: c.op, value: num(c.value) };
    case "indicator": return { type: "indicator", symbol: c.symbol.trim().toUpperCase(), tf: c.tf, field: c.field, op: c.op === "gte" ? "gte" : "lte", value: num(c.value) };
    case "news_window": return { type: "news_window", impact: c.impact, within_min: Number(c.within_min), phase: c.phase, ...(c.country?.trim() ? { country: c.country.trim() } : {}) };
    case "account": return { type: "account", account_id: c.account_id, metric: c.metric, op: c.op === "gte" ? "gte" : "lte", value: num(c.value) };
    default: return null;
  }
}

const toLocalInput = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};

function Seg2({ label, value, onChange, options, className }) {
  return (
    <div className="label"><span>{label}</span>
      <div className={cn("seg scroll", className)} role="group" aria-label={label}>
        {options.map(([v, l]) => <button key={v} type="button" aria-pressed={value === v} onClick={() => onChange(v)}>{l}</button>)}
      </div>
    </div>
  );
}

function CondEditor({ c, i, errs, set, remove, canRemove, accounts, multi, dfl }) {
  const symbols = useSymbols();
  const s = String(c.symbol || "").trim().toUpperCase();
  const quote = useQuotes(c.type === "price" && SYMBOL_RE.test(s) ? [s] : undefined);
  const cur = quote.data?.[0];
  const lid = useId();
  const up = (patch) => set(i, patch);
  const unsupported = !COND_TYPES.includes(c.type);
  if (unsupported) {
    return (
      <div className="rounded-xl border border-line bg-panel2 p-3 flex items-center gap-2 text-[13px]">
        <div className="min-w-0 flex-1"><b>{t("Điều kiện {n}", { n: i + 1 })}</b>: {summarizeCond(c._orig || c)} <span className="text-faint">({t("giữ nguyên, chưa sửa được trên giao diện này")})</span></div>
        {canRemove && <button type="button" className="ibtn" onClick={() => remove(i)} aria-label={t("Xoá điều kiện {n}", { n: i + 1 })}><Trash2 size={16} aria-hidden="true" /></button>}
      </div>
    );
  }
  const symField = (
    <Field label={t("Mã")} error={errs.symbol} hint={cur ? t("Giá hiện tại {p}", { p: price(s, cur.bid ?? cur.ask) }) : undefined}>
      <input className="field" list={lid} value={c.symbol} onChange={(e) => up({ symbol: e.target.value })} autoCapitalize="characters" autoComplete="off" />
      <datalist id={lid}>{(symbols.data || []).slice(0, 80).map((x) => <option key={x.symbol} value={x.symbol}>{x.name}</option>)}</datalist>
    </Field>
  );
  const valField = (lab, hint) => (
    <Field label={lab} error={errs.value} hint={hint}><input className="field num" inputMode="decimal" value={c.value} onChange={(e) => up({ value: e.target.value })} autoComplete="off" /></Field>
  );
  return (
    <fieldset className="rounded-xl border border-line bg-panel2 p-3 grid gap-3 m-0 min-w-0">
      <legend className="px-1 text-[12.5px] font-semibold flex items-center gap-2">
        {multi ? t("Điều kiện {n}", { n: i + 1 }) : t("Điều kiện")}
      </legend>
      <div className="flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <Seg2 label={t("Loại điều kiện")} value={c.type} onChange={(v) => up({ type: v, ...(blank(v, { account_id: dfl })), _k: c._k })} options={COND_TYPES.map((k) => [k, condTypeLabel(k)])} />
        </div>
        {canRemove && <button type="button" className="ibtn" onClick={() => remove(i)} aria-label={t("Xoá điều kiện {n}", { n: i + 1 })}><Trash2 size={16} aria-hidden="true" /></button>}
      </div>

      {c.type === "price" && (
        <>
          {symField}
          <Field label={t("Khi giá")}><select className="field" value={c.op} onChange={(e) => up({ op: e.target.value })}>
            {["gte", "lte", "cross_up", "cross_down"].map((o) => <option key={o} value={o}>{o === "gte" ? t("lên tới hoặc cao hơn (≥)") : o === "lte" ? t("xuống tới hoặc thấp hơn (≤)") : o === "cross_up" ? t("cắt lên trên mức") : t("cắt xuống dưới mức")}</option>)}
          </select></Field>
          {valField(t("Mức giá"))}
        </>
      )}
      {c.type === "pct_change" && (
        <>
          {symField}
          <Field label={t("Trong khoảng")}><select className="field" value={WINDOWS.includes(Number(c.window_min)) ? c.window_min : "custom"} onChange={(e) => up({ window_min: e.target.value === "custom" ? "45" : e.target.value })}>
            {WINDOWS.map((w) => <option key={w} value={w}>{winLabel(w)}</option>)}<option value="custom">{t("Tuỳ chọn (phút)")}</option>
          </select></Field>
          {!WINDOWS.includes(Number(c.window_min)) && <Field label={t("Số phút")} error={errs.window_min}><input className="field num" inputMode="numeric" value={c.window_min} onChange={(e) => up({ window_min: e.target.value })} /></Field>}
          <Field label={t("Điều kiện")}><select className="field" value={c.op} onChange={(e) => up({ op: e.target.value })}>
            <option value="abs_gte">{t("Biến động (lên hoặc xuống) từ")}</option><option value="gte">{t("Tăng từ (≥)")}</option><option value="lte">{t("Giảm từ (≤, nhập số âm)")}</option>
          </select></Field>
          {valField(t("Ngưỡng (%)"))}
        </>
      )}
      {c.type === "indicator" && (
        <>
          {symField}
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("Khung thời gian")}><select className="field" value={c.tf} onChange={(e) => up({ tf: e.target.value })}>{TFS.map((x) => <option key={x}>{x}</option>)}</select></Field>
            <Field label={t("Chỉ báo")}><select className="field" value={c.field} onChange={(e) => up({ field: e.target.value })}>{FIELDS.map((x) => <option key={x} value={x}>{fieldLabel(x)}</option>)}</select></Field>
          </div>
          <Field label={t("Khi giá trị")}><select className="field" value={c.op === "lte" ? "lte" : "gte"} onChange={(e) => up({ op: e.target.value })}><option value="gte">{t("lên tới hoặc cao hơn (≥)")}</option><option value="lte">{t("xuống tới hoặc thấp hơn (≤)")}</option></select></Field>
          {valField(t("Ngưỡng"))}
        </>
      )}
      {c.type === "news_window" && (
        <>
          <Seg2 label={t("Mức tác động")} value={c.impact} onChange={(v) => up({ impact: v })} options={[["high", t("Cao")], ["med", t("Vừa")]]} />
          <Seg2 label={t("Thời điểm")} value={c.phase} onChange={(v) => up({ phase: v })} options={[["upcoming", t("Sắp ra")], ["active", t("Đang diễn ra")]]} />
          <Field label={t("Trong vòng (phút)")} error={errs.within_min} hint={t("Từ 5 đến 720 phút trước khi tin ra.")}><input className="field num" inputMode="numeric" value={c.within_min} onChange={(e) => up({ within_min: e.target.value })} /></Field>
          <Field label={t("Quốc gia (tuỳ chọn)")} error={errs.country} hint={t("Ví dụ US, EU, UK. Để trống = mọi quốc gia.")}><input className="field" value={c.country} onChange={(e) => up({ country: e.target.value })} autoCapitalize="characters" /></Field>
        </>
      )}
      {c.type === "account" && (
        <>
          <Field label={t("Tài khoản")} error={errs.account_id} hint={t("Chỉ chọn được tài khoản của chính bạn.")}>
            <select className="field" value={c.account_id} onChange={(e) => up({ account_id: e.target.value })}>
              {!c.account_id && <option value="">{t("Chọn tài khoản...")}</option>}
              {accounts.map((a) => <option key={a.id} value={a.id}>{accountTitle(a)}</option>)}
            </select>
          </Field>
          <Field label={t("Chỉ số")}><select className="field" value={c.metric} onChange={(e) => up({ metric: e.target.value })}>{METRICS.map((m) => <option key={m} value={m}>{metricLabel(m)}</option>)}</select></Field>
          <Field label={t("Khi chỉ số")}><select className="field" value={c.op === "gte" ? "gte" : "lte"} onChange={(e) => up({ op: e.target.value })}><option value="lte">{t("xuống tới hoặc thấp hơn (≤)")}</option><option value="gte">{t("lên tới hoặc cao hơn (≥)")}</option></select></Field>
          {valField(t("Ngưỡng"), c.metric === "floating_pl_pct" ? t("Lỗ nhập số âm, ví dụ -3 = lỗ 3% số dư.") : c.metric === "equity_drawdown_24h" ? t("Sụt vốn nhập số dương, ví dụ 5 = sụt 5% từ đỉnh 24 giờ.") : t("Ví dụ 300 = margin còn 300%."))}
        </>
      )}
    </fieldset>
  );
}

/** Dịch lỗi 422 của máy chủ (mảng {loc,msg}) thành danh sách dòng dễ đọc. */
export function serverErrorLines(e) {
  const d = e?.detail;
  if (Array.isArray(d)) {
    return d.map((x) => {
      const loc = (x.loc || []).filter((p) => p !== "body");
      const ci = loc.indexOf("conditions");
      const where = ci >= 0 && Number.isInteger(loc[ci + 1]) ? t("Điều kiện {n}", { n: loc[ci + 1] + 1 }) : loc.includes("name") ? t("Tên") : loc.includes("channels") ? t("Kênh nhận") : loc.includes("cooldown_min") ? t("Thời gian chờ") : loc.join(".");
      return `${where ? `${where}: ` : ""}${clean(String(x.msg || ""))}`;
    });
  }
  const m = detailText(d) || e?.message;
  return m ? [clean(m)] : [];
}

/** init: quy tắc máy chủ (sửa) | {preset} | null. dup: tạo bản sao (không có id). */
export default function RuleSheet({ init, preset, dup, accounts, activeId, count, onClose, onSaved }) {
  const edit = !!init?.id && !dup;
  const accIds = accounts.map((a) => a.id);
  const dfl = accounts.length === 1 ? accounts[0].id : (accIds.includes(activeId) ? activeId : "");
  const p = preset ? PRESETS[preset.kind]?.({ symbol: preset.symbol, account_id: dfl }) : null;
  const [name, setName] = useState(init ? (dup ? `${init.name} ${t("(bản sao)")}`.slice(0, 60) : init.name) : p?.name || "");
  const [conds, setConds] = useState(() => (init ? (init.conditions || []).map(fromCond) : p?.conds || [blank("price", { symbol: preset?.symbol })]));
  const [logic, setLogic] = useState(init?.logic || "and");
  const [level, setLevel] = useState(init?.level || p?.level || "warn");
  const [channels, setChannels] = useState(() => { const c = (init?.channels || ["app"]).filter((x) => x === "app" || x === "push"); return c.length ? c : ["app"]; });
  const [mode, setMode] = useState(init?.mode || p?.mode || "once");
  const [cool, setCool] = useState(String(Math.max(init?.cooldown_min ?? 60, MIN_COOLDOWN)));
  const [exp, setExp] = useState(toLocalInput(init?.expires_at));
  const [enabled, setEnabled] = useState(dup ? true : init?.enabled !== false);
  const [busy, setBusy] = useState(false);
  const [tried, setTried] = useState(false);
  const [lines, setLines] = useState([]);
  const [prev, setPrev] = useState(null);
  const [prevBusy, setPrevBusy] = useState(false);

  const setCond = (i, patch) => { setConds((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c))); setPrev(null); };
  const removeCond = (i) => { setConds((cs) => cs.filter((_, j) => j !== i)); setPrev(null); };
  const addCond = () => { setConds((cs) => [...cs, blank("price", { account_id: dfl })]); setPrev(null); };
  const condErrs = conds.map((c) => (COND_TYPES.includes(c.type) ? validateCond(c) : {}));
  const autoName = conds.length ? summarizeCond(COND_TYPES.includes(conds[0].type) ? conds[0] : conds[0]._orig).slice(0, 60) : "";
  const finalName = (name.trim() || autoName).slice(0, 60);
  const errs = {};
  if (!finalName) errs.name = t("Nhập tên cảnh báo.");
  if (!conds.length) errs.conds = t("Cần ít nhất một điều kiện.");
  if (!channels.length) errs.channels = t("Chọn ít nhất một kênh nhận.");
  const coolN = num(cool);
  if (mode === "repeat" && !(Number.isInteger(coolN) && coolN >= MIN_COOLDOWN && coolN <= 1440)) errs.cool = t("Thời gian chờ từ {lo} đến {hi} phút.", { lo: MIN_COOLDOWN, hi: 1440 });
  if (exp && !(new Date(exp).getTime() > Date.now())) errs.exp = t("Ngày hết hạn phải ở tương lai.");
  if (!edit && count >= MAX_RULES) errs.max = t("Bạn đã dùng hết {n} cảnh báo. Xoá bớt một cảnh báo để tạo mới.", { n: MAX_RULES });
  const invalid = Object.keys(errs).length > 0 || condErrs.some((e) => Object.keys(e).length);

  const payload = () => ({
    name: finalName, enabled, logic, level, channels, mode, cooldown_min: mode === "repeat" ? coolN : Math.max(num(cool) || 60, MIN_COOLDOWN),
    expires_at: exp ? new Date(exp).toISOString() : null, note: init?.note || "",
    conditions: conds.map((c) => (COND_TYPES.includes(c.type) ? toCond(c) : c._orig)),
  });
  const submit = async (e) => {
    e.preventDefault();
    setTried(true); setLines([]);
    if (invalid || busy) return;
    setBusy(true);
    try {
      const body = payload();
      if (edit) await apiWrite("PUT", `/user/rules/${init.id}`, body); else await apiWrite("POST", "/user/rules", body);
      await onSaved();
    } catch (x) { setLines(serverErrorLines(x)); setBusy(false); }
  };
  const doPreview = async () => {
    setTried(true); setLines([]);
    if (invalid) return;
    setPrevBusy(true);
    try { setPrev(await apiWrite("POST", "/user/rules/preview", payload())); } catch (x) { setPrev(null); setLines(serverErrorLines(x)); } finally { setPrevBusy(false); }
  };
  const toggleCh = (c) => setChannels((cs) => (cs.includes(c) ? cs.filter((x) => x !== c) : [...cs, c]));
  const shown = (k) => (tried ? errs[k] : null);

  return (
    <Sheet title={edit ? t("Sửa cảnh báo") : dup ? t("Nhân bản cảnh báo") : t("Tạo cảnh báo")} onClose={onClose}>
      <form className="grid gap-3.5" onSubmit={submit} noValidate>
        <p className="m-0 text-[13px] text-muted">{t("Cảnh báo chạy trên máy chủ, gửi tới ứng dụng và thiết bị của bạn kể cả khi đã đóng ứng dụng. Chỉ nhắc, không đặt hay đóng lệnh.")}</p>
        {errs.max && <Notice tone="warn">{errs.max}</Notice>}
        <Field label={t("Tên cảnh báo")} error={shown("name")} hint={name.trim() ? undefined : t("Để trống: tự đặt tên “{n}”.", { n: autoName || "—" })}>
          <input className="field" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} autoComplete="off" />
        </Field>

        {conds.map((c, i) => (
          <CondEditor key={c._k} c={c} i={i} errs={tried ? condErrs[i] : {}} set={setCond} remove={removeCond} canRemove={conds.length > 1} accounts={accounts} multi={conds.length > 1} dfl={dfl} />
        ))}
        {errs.conds && tried && <div role="alert" className="text-[12.5px] text-down">{errs.conds}</div>}
        {conds.length > 1 && <Seg2 label={t("Kích hoạt khi")} value={logic} onChange={setLogic} options={[["and", t("Tất cả điều kiện đúng")], ["or", t("Một trong các điều kiện đúng")]]} />}
        {conds.length < MAX_CONDS && <button type="button" className="btn sm justify-self-start" onClick={addCond}><Plus size={15} aria-hidden="true" /> {t("Thêm điều kiện")}</button>}

        <Seg2 label={t("Mức độ")} value={level} onChange={setLevel} options={[["info", t("Thông tin")], ["warn", t("Cảnh báo")], ["crit", t("Nghiêm trọng")]]} />
        <div className="label"><span>{t("Kênh nhận")}</span>
          <div className="flex flex-wrap gap-2" role="group" aria-label={t("Kênh nhận")}>
            {[["app", t("Trong ứng dụng")], ["push", t("Thông báo đẩy")]].map(([k, l]) => (
              <label key={k} className="inline-flex items-center gap-2 min-h-[44px] px-3 rounded-[10px] border border-line2 bg-panel2 cursor-pointer text-[13px] text-fg font-medium">
                <input type="checkbox" className="w-4 h-4 accent-[var(--accent)]" checked={channels.includes(k)} onChange={() => toggleCh(k)} /> {l}
              </label>))}
          </div>
          {shown("channels") && <span className="text-[12px] text-down font-normal" role="alert">{errs.channels}</span>}
        </div>
        <Seg2 label={t("Số lần báo")} value={mode} onChange={setMode} options={[["once", t("Một lần rồi tự tắt")], ["repeat", t("Mỗi lần điều kiện đúng lại")]]} />
        {mode === "repeat" && (
          <Field label={t("Thời gian chờ giữa hai lần báo (phút)")} error={shown("cool")} hint={t("Tối thiểu {n} phút để tránh báo dồn dập.", { n: MIN_COOLDOWN })}>
            <input className="field num" inputMode="numeric" value={cool} onChange={(e) => setCool(e.target.value)} />
          </Field>
        )}
        <Field label={t("Hết hạn (tuỳ chọn)")} error={shown("exp")} hint={t("Sau thời điểm này cảnh báo tự dừng. Để trống = không hết hạn.")}>
          <input className="field" type="datetime-local" value={exp} onChange={(e) => setExp(e.target.value)} />
        </Field>

        <div className="rounded-xl border border-line p-3 grid gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <b className="text-[13px]">{t("Xem trước giá trị hiện tại")}</b>
            <button type="button" className="btn sm ml-auto" onClick={doPreview} disabled={prevBusy}><Eye size={15} aria-hidden="true" /> {prevBusy ? t("Đang kiểm tra...") : t("Kiểm tra ngay")}</button>
          </div>
          {prev ? (
            <div className="grid gap-1.5" aria-live="polite">
              {(prev.conditions || []).map((r, i) => (
                <div key={i} className="flex items-start gap-2 text-[13px]">
                  <Chip tone={r.ok === true ? "up" : r.ok === false ? "" : "accent"}>{r.ok === true ? t("Đang thoả") : r.ok === false ? t("Chưa thoả") : t("Chưa có dữ liệu")}</Chip>
                  <span className="min-w-0 break-words">{clean(r.text) || summarizeCond(conds[i] || {})}{r.stale ? <span className="text-faint"> · {t("dữ liệu có thể đã cũ")}</span> : null}</span>
                </div>))}
              <div className="text-[12.5px] text-muted">{prev.result === true ? t("Nếu lưu bây giờ, điều kiện đang đúng nên có thể báo ngay khi máy chủ kiểm tra.") : t("Điều kiện hiện chưa đúng. Cảnh báo sẽ báo khi điều kiện đúng.")}</div>
            </div>
          ) : <div className="text-[12.5px] text-muted">{t("Xem điều kiện đang đúng hay sai ở thời điểm này, trước khi lưu.")}</div>}
        </div>

        {lines.length > 0 && <Notice tone="down" title={t("Máy chủ từ chối lưu")}><ul className="m-0 pl-4">{lines.map((l, i) => <li key={i}>{l}</li>)}</ul></Notice>}
        <div className="flex items-center gap-2">
          <button className="btn primary flex-1" type="submit" disabled={busy || !!errs.max}>{busy ? t("Đang lưu...") : edit ? t("Lưu thay đổi") : t("Tạo cảnh báo")}</button>
          <button className="btn" type="button" onClick={onClose}>{t("Huỷ")}</button>
        </div>
        {tried && invalid && <div role="alert" className="text-[12.5px] text-down">{t("Còn mục chưa hợp lệ, xem các dòng báo đỏ phía trên.")}</div>}
      </form>
    </Sheet>
  );
}
