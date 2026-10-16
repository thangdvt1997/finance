// Trang Cảnh báo: quy tắc của tôi (danh sách + trình tạo/sửa) và lịch sử kích hoạt. Chỉ ghi qua /user/rules (không có lệnh giao dịch).
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BellPlus, Check, CircleHelp, Eye, Pencil, Plus, Trash2, X } from "lucide-react";
import { Async, Chip, Panel, cn } from "./ui";
import { Dialog } from "./dialog";
import { apiWrite } from "../lib/api";
import { useSymbols } from "../lib/queries";
import { dateTime, rel, clean } from "../lib/format";
import {
  ACC_METRICS, CHANNELS, COND_TYPES, IND, LEVELS, MAX_COND, OPS, PRESETS, STATE_FIELDS, STATUS, TF_LIST,
  buildPayload, emptyForm, mapServerErrors, newCond, ruleToForm, ruleToIn, summarize, useRuleEvents, useRules,
} from "../lib/rules";

// ---------- trường nhập ----------
function Field({ label, error, hint, className, children, id }) {
  return (
    <div className={cn("grid gap-1 content-start min-w-0", className)}>
      <label htmlFor={id} className="text-[11.5px] text-muted">{label}</label>
      {children}
      {hint && !error && <span className="text-[11px] text-faint">{hint}</span>}
      {error && <span className="text-[11.5px] text-down" role="alert">{error}</span>}
    </div>
  );
}
const inv = (err) => (err ? { "aria-invalid": true } : {});

function Sel({ id, value, onChange, options, ...rest }) {
  return (
    <select id={id} className="field w-full" value={value} onChange={(e) => onChange(e.target.value)} {...rest}>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
}

function CondEditor({ c, i, set, remove, errors, canRemove }) {
  const uid = useId();
  const id = (k) => `${uid}-${k}`;
  const er = (k) => errors[`conditions.${i}.${k}`];
  const up = (patch) => set(i, { ...c, ...patch });
  const sym = (
    <Field label="Mã" id={id("symbol")} error={er("symbol")}>
      <input id={id("symbol")} className="field w-full" list="rule-symbols" value={c.symbol || ""} onChange={(e) => up({ symbol: e.target.value })} autoComplete="off" spellCheck={false} placeholder="EURUSD" {...inv(er("symbol"))} />
    </Field>
  );
  const val = (label = "Giá trị", hint) => (
    <Field label={label} id={id("value")} error={er("value")} hint={hint}>
      <input id={id("value")} className="field w-full num" inputMode="decimal" value={c.value ?? ""} onChange={(e) => up({ value: e.target.value })} {...inv(er("value"))} />
    </Field>
  );
  const tf = <Field label="Khung" id={id("tf")}><Sel id={id("tf")} value={c.tf} onChange={(v) => up({ tf: v })} options={TF_LIST.map((t) => [t, t])} /></Field>;
  const entries = (o) => Object.entries(o);
  let body = null;
  switch (c.type) {
    case "price":
      body = <>{sym}
        <Field label="Điều kiện" id={id("op")}><Sel id={id("op")} value={c.op} onChange={(v) => up({ op: v })} options={[["gte", "Giá ≥ mức"], ["lte", "Giá ≤ mức"], ["cross_up", "Vừa cắt lên trên mức"], ["cross_down", "Vừa cắt xuống dưới mức"]]} /></Field>
        {val("Mức giá (mid)")}</>;
      break;
    case "pct_change":
      body = <>{sym}
        <Field label="Cửa sổ (phút)" id={id("w")} error={er("window_min")}><input id={id("w")} className="field w-full num" inputMode="numeric" value={c.window_min} onChange={(e) => up({ window_min: e.target.value })} {...inv(er("window_min"))} /></Field>
        <Field label="Điều kiện" id={id("op")}><Sel id={id("op")} value={c.op} onChange={(v) => up({ op: v })} options={[["abs_gte", "Biến động tuyệt đối ≥"], ["gte", "Tăng ≥"], ["lte", "Thay đổi ≤ (âm = giảm)"]]} /></Field>
        {val("Ngưỡng (%)")}</>;
      break;
    case "indicator":
      body = <>{sym}{tf}
        <Field label="Chỉ báo" id={id("f")}><Sel id={id("f")} value={c.field} onChange={(v) => up({ field: v })} options={entries(IND).map(([k, [l, u]]) => [k, u ? `${l} (${u})` : l])} /></Field>
        <Field label="Điều kiện" id={id("op")}><Sel id={id("op")} value={c.op} onChange={(v) => up({ op: v })} options={[["gte", "≥"], ["lte", "≤"]]} /></Field>
        {val()}</>;
      break;
    case "state": {
      const f = STATE_FIELDS[c.field] || STATE_FIELDS.trend;
      body = <>{sym}{tf}
        <Field label="Loại trạng thái" id={id("f")}><Sel id={id("f")} value={c.field} onChange={(v) => up({ field: v, is: Object.keys(STATE_FIELDS[v][1])[0] })} options={entries(STATE_FIELDS).map(([k, [l]]) => [k, l])} /></Field>
        <Field label="Là" id={id("is")}><Sel id={id("is")} value={c.is} onChange={(v) => up({ is: v })} options={entries(f[1])} /></Field></>;
      break;
    }
    case "news_window":
      body = <>
        <Field label="Tác động" id={id("imp")}><Sel id={id("imp")} value={c.impact} onChange={(v) => up({ impact: v })} options={[["high", "Cao"], ["med", "Vừa"]]} /></Field>
        <Field label="Giai đoạn" id={id("ph")}><Sel id={id("ph")} value={c.phase} onChange={(v) => up({ phase: v })} options={[["upcoming", "Sắp ra trong N phút tới"], ["active", "Đang trong cửa sổ T-15..T+30"]]} /></Field>
        <Field label="Trong vòng (phút)" id={id("wi")} error={er("within_min")} hint="5–720"><input id={id("wi")} className="field w-full num" inputMode="numeric" value={c.within_min} onChange={(e) => up({ within_min: e.target.value })} {...inv(er("within_min"))} /></Field>
        <Field label="Quốc gia" id={id("co")} error={er("country")} hint="Để trống = mọi nước"><input id={id("co")} className="field w-full" value={c.country || ""} onChange={(e) => up({ country: e.target.value })} placeholder="US" maxLength={3} {...inv(er("country"))} /></Field></>;
      break;
    case "sentiment": {
      const flip = String(c.op).startsWith("flip");
      body = <>{sym}
        <Field label="Cửa sổ (giờ)" id={id("wh")} error={er("window_h")}><input id={id("wh")} className="field w-full num" inputMode="numeric" value={c.window_h} onChange={(e) => up({ window_h: e.target.value })} {...inv(er("window_h"))} /></Field>
        <Field label="Điều kiện" id={id("op")}><Sel id={id("op")} value={c.op} onChange={(v) => up({ op: v })} options={[["gte", "Sentiment ≥"], ["lte", "Sentiment ≤"], ["flip_up", "Đổi dấu sang dương"], ["flip_down", "Đổi dấu sang âm"]]} /></Field>
        {!flip && val("Ngưỡng (−1…1)")}</>;
      break;
    }
    case "account":
      body = <>
        <Field label="Số tài khoản" id={id("acc")} hint="Để trống = mọi tài khoản"><input id={id("acc")} className="field w-full" value={c.account_id || ""} onChange={(e) => up({ account_id: e.target.value })} autoComplete="off" /></Field>
        <Field label="Chỉ số" id={id("m")}><Sel id={id("m")} value={c.metric} onChange={(v) => up({ metric: v })} options={entries(ACC_METRICS).map(([k, [l, u]]) => [k, `${l} (${u})`])} /></Field>
        <Field label="Điều kiện" id={id("op")}><Sel id={id("op")} value={c.op} onChange={(v) => up({ op: v })} options={[["gte", "≥"], ["lte", "≤"]]} /></Field>
        {val("Ngưỡng (%)")}</>;
      break;
    default: break;
  }
  return (
    <fieldset className="m-0 rounded-md border border-line bg-panel2 p-3 min-w-0">
      <legend className="px-1 text-[12px] font-semibold text-fg">Điều kiện {i + 1}</legend>
      <div className="flex items-end gap-2 mb-2">
        <Field label="Loại" id={id("type")} className="flex-1">
          <Sel id={id("type")} value={c.type} onChange={(v) => set(i, newCond(v, c.symbol || "EURUSD"))} options={entries(COND_TYPES)} />
        </Field>
        <button type="button" className="btn !px-2" onClick={() => remove(i)} disabled={!canRemove} aria-label={`Xoá điều kiện ${i + 1}`}><Trash2 size={14} aria-hidden="true" /></button>
      </div>
      <div className="grid gap-2 grid-cols-1 min-[420px]:grid-cols-2">{body}</div>
      {c.type === "account" && <p className="m-0 mt-2 text-[11.5px] text-faint">Chỉ đọc số liệu tài khoản MT; không có thao tác giao dịch.</p>}
    </fieldset>
  );
}

// ---------- kết quả xem thử ----------
function PreviewBox({ res, loading, error }) {
  if (loading) return <p className="m-0 text-muted text-[12.5px]" role="status">Đang lấy giá trị hiện tại…</p>;
  if (error) return <p className="m-0 text-down text-[12.5px]" role="alert">{error}</p>;
  if (!res) return null;
  const tone = res.result === true ? "up" : res.result === false ? "" : "accent";
  return (
    <div className="rounded-md border border-line2 bg-bg p-2 grid gap-1" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-[12.5px]">
        <b>Kết quả hiện tại:</b>
        <Chip tone={tone}>{res.result === true ? "Đang thoả" : res.result === false ? "Chưa thoả" : "Chưa đủ dữ liệu"}</Chip>
      </div>
      <ul className="m-0 p-0 list-none grid gap-1">
        {(res.conditions || []).map((x, k) => (
          <li key={k} className="flex items-start gap-2 text-[12.5px]">
            <span className={cn("shrink-0 mt-[2px]", x.ok === true ? "text-up" : x.ok === false ? "text-faint" : "text-accent")} aria-label={x.ok === true ? "Thoả" : x.ok === false ? "Chưa thoả" : "Không rõ"}>
              {x.ok === true ? <Check size={14} aria-hidden="true" /> : x.ok === false ? <X size={14} aria-hidden="true" /> : <CircleHelp size={14} aria-hidden="true" />}
            </span>
            <span className="min-w-0">{x.text}{x.value != null && x.value !== "" && <span className="num text-muted"> · {String(x.value)}</span>}{x.stale && <Chip className="ml-1" tone="accent" title="Dữ liệu đã cũ">cũ</Chip>}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------- trình tạo / sửa ----------
function RuleEditor({ open, onClose, initial, editingId, limits }) {
  const qc = useQueryClient();
  const [f, setF] = useState(initial);
  const [errors, setErrors] = useState({});
  const [general, setGeneral] = useState([]);
  const [busy, setBusy] = useState(false);
  const [pv, setPv] = useState({ loading: false, res: null, error: "" });
  const uid = useId();
  const sy = useSymbols();
  const body = useRef(null);
  useEffect(() => { if (open) { setF(initial); setErrors({}); setGeneral([]); setPv({ loading: false, res: null, error: "" }); } }, [open, initial]);
  const maxC = limits?.max_conditions || MAX_COND;
  const chans = limits?.channels?.length ? limits.channels : Object.keys(CHANNELS);
  const upd = (patch) => setF((x) => ({ ...x, ...patch }));
  const setCond = (i, c) => setF((x) => ({ ...x, conditions: x.conditions.map((o, k) => (k === i ? c : o)) }));
  const rmCond = (i) => setF((x) => ({ ...x, conditions: x.conditions.filter((_, k) => k !== i) }));
  const toggleCh = (ch) => upd({ channels: f.channels.includes(ch) ? f.channels.filter((x) => x !== ch) : [...f.channels, ch] });

  function failFocus(errs) {
    requestAnimationFrame(() => body.current?.querySelector("[aria-invalid='true']")?.focus());
    return errs;
  }
  async function preview() {
    const { payload, errors: er } = buildPayload(f);
    if (Object.keys(er).length) { setErrors(er); failFocus(er); return; }
    setPv({ loading: true, res: null, error: "" });
    try {
      const r = await apiWrite("POST", "/user/rules/preview", payload);
      setPv({ loading: false, res: r, error: "" });
    } catch (e) {
      const m = mapServerErrors(e);
      setErrors((x) => ({ ...x, ...m.errors }));
      setPv({ loading: false, res: null, error: e.status === 422 ? "Quy tắc chưa hợp lệ, xem các trường bị đánh dấu." : e.message });
    }
  }
  async function save() {
    const { payload, errors: er } = buildPayload(f);
    setErrors(er); setGeneral([]);
    if (Object.keys(er).length) { failFocus(er); return; }
    setBusy(true);
    try {
      await (editingId ? apiWrite("PUT", `/user/rules/${editingId}`, payload) : apiWrite("POST", "/user/rules", payload));
      await qc.invalidateQueries({ queryKey: ["user-rules"] });
      onClose(true);
    } catch (e) {
      if (e.status === 422 || e.status === 409) { const m = mapServerErrors(e); setErrors(m.errors); setGeneral(m.general); failFocus(m.errors); }
      else setGeneral([e.message]);
    } finally { setBusy(false); }
  }
  const errList = Object.entries(errors);
  return (
    <Dialog open={open} onClose={() => onClose(false)} variant="drawer" title={editingId ? "Sửa quy tắc cảnh báo" : "Tạo quy tắc cảnh báo"} initialFocus="[data-autofocus]"
      footer={<>
        <button type="button" className="btn mr-auto" onClick={preview} disabled={busy || pv.loading}><Eye size={14} aria-hidden="true" /> Xem giá trị hiện tại</button>
        <button type="button" className="btn" onClick={() => onClose(false)}>Huỷ</button>
        <button type="button" className="btn !bg-accent !text-[var(--accent-fg)] !border-transparent font-semibold" onClick={save} disabled={busy}>{busy ? "Đang lưu…" : "Lưu quy tắc"}</button>
      </>}>
      <form ref={body} className="p-3 grid gap-3" onSubmit={(e) => { e.preventDefault(); save(); }} noValidate>
        <datalist id="rule-symbols">{(sy.data || []).slice(0, 300).map((s) => <option key={s.symbol} value={s.symbol} />)}</datalist>
        {(general.length > 0 || (errList.length > 0 && !errList.every(([k]) => k === "name" || k.startsWith("conditions") || ["cooldown_min", "expires_local", "channels", "note"].includes(k)))) && (
          <div role="alert" className="rounded-md border border-[var(--down)] bg-[var(--down-bg)] p-2 text-[12.5px] flex gap-2">
            <AlertTriangle size={15} className="text-down shrink-0 mt-[2px]" aria-hidden="true" />
            <div>{general.map((g, i) => <div key={i}>{g}</div>)}{errList.filter(([k]) => !["name", "cooldown_min", "expires_local", "channels", "note"].includes(k) && !k.startsWith("conditions.")).map(([k, m]) => <div key={k}>{k}: {m}</div>)}</div>
          </div>
        )}
        <Field label="Tên quy tắc" id={`${uid}-name`} error={errors.name}>
          <input id={`${uid}-name`} data-autofocus className="field w-full" maxLength={80} value={f.name} onChange={(e) => upd({ name: e.target.value })} placeholder="VD: EURUSD vượt 1.1000" {...inv(errors.name)} />
        </Field>

        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[12.5px] text-muted" id={`${uid}-lg`}>Kích hoạt khi thoả</span>
          <div className="seg" role="group" aria-labelledby={`${uid}-lg`}>
            {[["and", "TẤT CẢ điều kiện (Và)"], ["or", "MỘT TRONG các điều kiện (Hoặc)"]].map(([v, l]) => (
              <button key={v} type="button" aria-pressed={f.logic === v} onClick={() => upd({ logic: v })}>{l}</button>
            ))}
          </div>
        </div>

        <div className="grid gap-2">
          {f.conditions.map((c, i) => <CondEditor key={i} c={c} i={i} set={setCond} remove={rmCond} errors={errors} canRemove={f.conditions.length > 1} />)}
          {errors.conditions && <span className="text-[11.5px] text-down" role="alert">{errors.conditions}</span>}
          <button type="button" className="btn justify-self-start" onClick={() => upd({ conditions: [...f.conditions, newCond("price", f.conditions.at(-1)?.symbol || "EURUSD")] })} disabled={f.conditions.length >= maxC}>
            <Plus size={14} aria-hidden="true" /> Thêm điều kiện <span className="text-faint">({f.conditions.length}/{maxC})</span>
          </button>
        </div>

        <div className="grid gap-3 grid-cols-1 min-[480px]:grid-cols-2">
          <Field label="Chế độ" id={`${uid}-mode`}>
            <Sel id={`${uid}-mode`} value={f.mode} onChange={(v) => upd({ mode: v })} options={[["once", "Một lần (xong thì dừng)"], ["repeat", "Lặp lại (có thời gian chờ)"]]} />
          </Field>
          <Field label="Chờ giữa 2 lần (phút)" id={`${uid}-cd`} error={errors.cooldown_min} hint={f.mode === "once" ? "Chỉ áp dụng cho chế độ lặp" : "1–1440"}>
            <input id={`${uid}-cd`} className="field w-full num" inputMode="numeric" value={f.cooldown_min} disabled={f.mode !== "repeat"} onChange={(e) => upd({ cooldown_min: e.target.value })} {...inv(errors.cooldown_min)} />
          </Field>
          <Field label="Hết hạn (giờ Việt Nam)" id={`${uid}-ex`} error={errors.expires_local} hint="Để trống = không hết hạn">
            <div className="flex gap-1">
              <input id={`${uid}-ex`} type="datetime-local" className="field w-full" value={f.expires_local} onChange={(e) => upd({ expires_local: e.target.value })} {...inv(errors.expires_local)} />
              {f.expires_local && <button type="button" className="btn !px-2" onClick={() => upd({ expires_local: "" })} aria-label="Bỏ hạn"><X size={14} aria-hidden="true" /></button>}
            </div>
          </Field>
          <Field label="Mức độ" id={`${uid}-lv`}>
            <Sel id={`${uid}-lv`} value={f.level} onChange={(v) => upd({ level: v })} options={Object.entries(LEVELS).map(([k, [l]]) => [k, l])} />
          </Field>
        </div>

        <fieldset className="m-0 p-0 border-0 min-w-0">
          <legend className="text-[11.5px] text-muted mb-1 p-0">Kênh nhận</legend>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {chans.map((ch) => (
              <label key={ch} className="flex items-center gap-2 text-[12.5px] cursor-pointer min-h-[1.75rem]">
                <input type="checkbox" checked={f.channels.includes(ch)} onChange={() => toggleCh(ch)} className="accent-[var(--accent)] w-4 h-4" /> {CHANNELS[ch] || ch}
              </label>
            ))}
          </div>
          {errors.channels && <span className="text-[11.5px] text-down" role="alert">{errors.channels}</span>}
        </fieldset>

        <Field label={`Ghi chú (${f.note.length}/200)`} id={`${uid}-note`} error={errors.note}>
          <textarea id={`${uid}-note`} className="field w-full !h-16 py-1" maxLength={200} value={f.note} onChange={(e) => upd({ note: e.target.value })} {...inv(errors.note)} />
        </Field>
        <label className="flex items-center gap-2 text-[12.5px] cursor-pointer">
          <input type="checkbox" checked={f.enabled} onChange={(e) => upd({ enabled: e.target.checked })} className="accent-[var(--accent)] w-4 h-4" /> Bật quy tắc ngay sau khi lưu
        </label>
        <PreviewBox {...pv} />
        <p className="m-0 text-[11.5px] text-faint">Cảnh báo chỉ để thông báo, không đặt lệnh và không phải khuyến nghị đầu tư.</p>
      </form>
    </Dialog>
  );
}

// ---------- danh sách quy tắc ----------
function Switch({ on, onChange, label, busy }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={busy} onClick={() => onChange(!on)}
      className={cn("relative inline-flex shrink-0 items-center w-9 h-5 rounded-full border transition-colors cursor-pointer p-0", on ? "bg-accent border-transparent" : "bg-panel2 border-line2", busy && "opacity-60")}>
      <span aria-hidden="true" className={cn("absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full transition-transform", on ? "translate-x-4 bg-[var(--accent-fg)]" : "bg-muted")} />
    </button>
  );
}

function RuleCard({ r, onEdit, onDelete, onToggle, busy }) {
  const [pv, setPv] = useState(null);
  const lv = LEVELS[r.level] || [r.level, ""];
  const st = STATUS[r.status] || [r.status, ""];
  async function preview() {
    setPv({ loading: true });
    try { setPv({ res: await apiWrite("POST", `/user/rules/${r.id}/preview`) }); }
    catch (e) { setPv({ error: e.message }); }
  }
  return (
    <li className={cn("rounded-md border border-line bg-panel2 p-3 grid gap-2 content-start min-w-0", r.status === "disabled" && "opacity-80")}>
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="font-semibold break-words">{r.name}</div>
          <div className="flex flex-wrap gap-1 mt-1">
            <Chip tone={st[1]}>{st[0]}</Chip>
            <Chip tone={lv[1]}>{lv[0]}</Chip>
            <Chip title={r.logic === "and" ? "Tất cả điều kiện phải thoả" : "Chỉ cần một điều kiện thoả"}>{r.logic === "and" ? "VÀ" : "HOẶC"}</Chip>
            <Chip>{r.mode === "once" ? "Một lần" : `Lặp · chờ ${r.cooldown_min}p`}</Chip>
          </div>
        </div>
        <Switch on={!!r.enabled} onChange={(v) => onToggle(r, v)} busy={busy} label={`${r.enabled ? "Tắt" : "Bật"} quy tắc ${r.name}`} />
      </div>
      <ul className="m-0 pl-4 text-[12.5px] text-fg grid gap-[2px]">{r.conditions.map((c, i) => <li key={i}>{summarize(c)}</li>)}</ul>
      {r.note && <p className="m-0 text-[12px] text-muted break-words">{r.note}</p>}
      <div className="text-[11.5px] text-faint flex flex-wrap gap-x-3 gap-y-[2px]">
        <span>Kênh: {r.channels.join(", ") || "—"}</span>
        <span>Hết hạn: {r.expires_at ? dateTime(r.expires_at) : "không"}</span>
        <span title={r.last_fired_at || ""}>Lần cuối: {r.last_fired_at ? `${dateTime(r.last_fired_at)} (${rel(r.last_fired_at)})` : "chưa"}</span>
        <span>Số lần: <b className="num text-muted">{r.fire_count ?? 0}</b></span>
      </div>
      {pv && <PreviewBox loading={pv.loading} res={pv.res} error={pv.error} />}
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn" onClick={preview} disabled={pv?.loading}><Eye size={14} aria-hidden="true" /> Xem giá trị hiện tại</button>
        <button type="button" className="btn" onClick={() => onEdit(r)}><Pencil size={14} aria-hidden="true" /> Sửa</button>
        <button type="button" className="btn" onClick={() => onDelete(r)} aria-label={`Xoá quy tắc ${r.name}`}><Trash2 size={14} aria-hidden="true" /> Xoá</button>
      </div>
    </li>
  );
}

export function RulesTab({ prefill, onPrefillDone }) {
  const q = useRules();
  const qc = useQueryClient();
  const [editor, setEditor] = useState({ open: false, initial: null, id: null });
  const [del, setDel] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [msg, setMsg] = useState("");
  const limits = q.data?.limits;

  const openNew = (patch) => setEditor({ open: true, initial: { ...emptyForm(), ...(patch || {}) }, id: null });
  useEffect(() => {
    if (!prefill) return;
    const p = PRESETS[0].build(prefill.symbol || "EURUSD");
    if (prefill.price) p.conditions = [{ ...p.conditions[0], value: prefill.price, op: prefill.op || "gte" }]; // từ Ctrl-K: "cảnh báo eurusd 1.0850"
    openNew(p);
    onPrefillDone?.();
  }, [prefill]); // eslint-disable-line react-hooks/exhaustive-deps

  async function toggle(r, enabled) {
    setBusyId(r.id); setMsg("");
    try { await apiWrite("PUT", `/user/rules/${r.id}`, ruleToIn(r, { enabled })); await qc.invalidateQueries({ queryKey: ["user-rules"] }); }
    catch (e) { setMsg(`Không đổi được trạng thái "${r.name}": ${e.message}`); }
    finally { setBusyId(null); }
  }
  async function remove() {
    const r = del;
    setBusyId(r.id); setMsg("");
    try { await apiWrite("DELETE", `/user/rules/${r.id}`); await qc.invalidateQueries({ queryKey: ["user-rules"] }); setDel(null); }
    catch (e) { setMsg(`Không xoá được "${r.name}": ${e.message}`); setDel(null); }
    finally { setBusyId(null); }
  }
  const count = q.data?.items?.length ?? 0;
  const max = limits?.max_rules ?? 50;
  const initial = useMemo(() => editor.initial, [editor.initial]);

  return (
    <div className="grid gap-3">
      <Panel title="Quy tắc của tôi" icon={BellPlus}
        right={<><span className="text-[11.5px] text-faint num" aria-label={`${count} trên ${max} quy tắc`}>{count}/{max}</span>
          <button type="button" className="btn !bg-accent !text-[var(--accent-fg)] !border-transparent font-semibold" onClick={() => openNew()} disabled={count >= max}><Plus size={14} aria-hidden="true" /> Tạo quy tắc</button></>}>
        {msg && <div role="alert" className="mb-3 text-down text-[12.5px] flex gap-2"><AlertTriangle size={15} className="shrink-0 mt-[2px]" aria-hidden="true" />{msg}</div>}
        <Async q={q} rows={4} empty="Chưa có quy tắc nào." hint="Chọn một mẫu bên dưới hoặc bấm “Tạo quy tắc”.">
          {(d) => (
            <ul className="m-0 p-0 list-none grid grid-cols-[repeat(auto-fill,minmax(min(100%,26rem),1fr))] gap-3">
              {d.items.map((r) => <RuleCard key={r.id} r={r} busy={busyId === r.id} onToggle={toggle} onEdit={(x) => setEditor({ open: true, initial: ruleToForm(x), id: x.id })} onDelete={setDel} />)}
            </ul>
          )}
        </Async>
      </Panel>

      <Panel title="Mẫu nhanh" icon={Plus}>
        <ul className="m-0 p-0 list-none grid grid-cols-[repeat(auto-fill,minmax(min(100%,13rem),1fr))] gap-2">
          {PRESETS.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => openNew(p.build())} disabled={count >= max}
                className="w-full text-left rounded-md border border-line bg-panel2 p-2 cursor-pointer text-fg font-[inherit] hover:border-muted disabled:opacity-50 grid gap-[2px]">
                <b className="text-[13px]">{p.title}</b>
                <span className="text-[11.5px] text-muted">{p.sub}</span>
              </button>
            </li>
          ))}
        </ul>
      </Panel>

      {editor.open && <RuleEditor open onClose={() => setEditor({ open: false, initial: null, id: null })} initial={initial} editingId={editor.id} limits={limits} />}

      <Dialog open={!!del} onClose={() => setDel(null)} title="Xoá quy tắc?"
        footer={<><button type="button" className="btn" onClick={() => setDel(null)} data-autofocus>Giữ lại</button>
          <button type="button" className="btn !bg-[var(--down)] !text-white !border-transparent font-semibold" onClick={remove} disabled={busyId === del?.id}>Xoá vĩnh viễn</button></>}>
        <p className="m-0 p-3 text-[13px]">Quy tắc <b>{del?.name}</b> và cấu hình của nó sẽ bị xoá. Lịch sử kích hoạt cũ vẫn được giữ.</p>
      </Dialog>
    </div>
  );
}

// ---------- lịch sử kích hoạt ----------
function Snap({ s }) {
  const e = Object.entries(s || {}).filter(([, v]) => v != null && typeof v !== "object");
  if (!e.length) return <span className="text-faint">—</span>;
  return (
    <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-2 gap-y-[1px] text-[11.5px]">
      {e.slice(0, 8).map(([k, v]) => (<span key={k} className="contents"><dt className="text-faint">{k}</dt><dd className="m-0 num break-all">{typeof v === "number" ? +v.toPrecision(8) : String(v)}</dd></span>))}
    </dl>
  );
}

export function EventsTab() {
  const rules = useRules();
  const [rid, setRid] = useState("");
  const q = useRuleEvents(rid || undefined, 100);
  const uid = useId();
  return (
    <Panel title="Lịch sử kích hoạt" icon={BellPlus} pad={false} fill bodyClass="flex flex-col"
      right={<><label htmlFor={uid} className="sr-only">Lọc theo quy tắc</label>
        <select id={uid} className="field max-w-[14rem]" value={rid} onChange={(e) => setRid(e.target.value)}>
          <option value="">Mọi quy tắc</option>
          {(rules.data?.items || []).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select></>}>
      <div className="p-3 scroll-y">
        <Async q={q} rows={5} empty="Chưa có lần kích hoạt nào." hint="Khi một quy tắc thoả điều kiện, giá trị chốt sẽ được lưu ở đây.">
          {(d) => (
            <div className="scroll-x">
              <table className="tbl">
                <thead><tr><th>Thời điểm</th><th>Quy tắc</th><th>Nội dung</th><th>Giá trị chốt</th><th>Gửi</th></tr></thead>
                <tbody>
                  {d.items.map((e) => (
                    <tr key={e.id} className="align-top">
                      <td className="whitespace-nowrap"><div>{dateTime(e.fired_at)}</div><div className="text-[11px] text-faint">{rel(e.fired_at)}</div></td>
                      <td className="min-w-[8rem]"><div className="font-semibold">{e.rule_name}</div><Chip tone={LEVELS[e.level]?.[1]}>{LEVELS[e.level]?.[0] || e.level}</Chip></td>
                      <td className="min-w-[12rem]"><div>{clean(e.title)}</div>{e.body && <div className="text-muted text-[12px] whitespace-pre-line">{clean(e.body)}</div>}</td>
                      <td className="min-w-[10rem]"><Snap s={e.snapshot} /></td>
                      <td><div className="flex flex-wrap gap-1">{(e.channels || []).map((c) => <Chip key={c}>{c}</Chip>)}<Chip tone={e.delivered ? "up" : e.delivered === false ? "down" : ""}>{e.delivered ? "Đã gửi" : e.delivered === false ? "Lỗi gửi" : "Chưa rõ"}</Chip></div></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Async>
      </div>
    </Panel>
  );
}
