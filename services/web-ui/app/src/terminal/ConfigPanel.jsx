// Bảng cấu hình widget: tự dựng form từ meta.configSchema + tiêu đề + kênh liên kết.
import { useId } from "react";
import { Dialog } from "../components/dialog";
import { cn } from "../components/ui";
import { CHANNELS } from "./store";
import { ChannelDot, SymbolInput } from "./ui";

const optVal = (o) => (typeof o === "object" ? o.value : o);
const optLab = (o) => (typeof o === "object" ? o.label : String(o));

function Field({ f, value, onChange }) {
  const id = useId();
  const v = value ?? f.default;
  const lab = <label htmlFor={id} className="block text-[12px] text-muted mb-1">{f.label}</label>;
  let ctl;
  switch (f.type) {
    case "symbol": ctl = <SymbolInput value={v} onChange={onChange} label={f.label} className="w-full" />; break;
    case "symbols":
      ctl = <textarea id={id} className="field w-full !h-20 py-1.5" spellCheck={false} defaultValue={(v || []).join(", ")} placeholder="EURUSD, GBPUSD, XAUUSD"
        onBlur={(e) => onChange(e.target.value.split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter((s) => /^[A-Za-z0-9:._-]{1,32}$/.test(s)).slice(0, 80))} />;
      break;
    case "text": ctl = <input id={id} className="field w-full" value={v ?? ""} placeholder={f.placeholder} maxLength={f.max || 80} onChange={(e) => onChange(e.target.value)} />; break;
    case "textarea": ctl = <textarea id={id} className="field w-full !h-24 py-1.5" value={v ?? ""} maxLength={f.max || 1500} onChange={(e) => onChange(e.target.value)} />; break;
    case "number": ctl = <input id={id} type="number" className="field w-full" value={v ?? ""} min={f.min} max={f.max} step={f.step || 1}
      onChange={(e) => { const n = e.target.value === "" ? undefined : Number(e.target.value); if (n === undefined || Number.isFinite(n)) onChange(n); }} />; break;
    case "select": ctl = (
      <select id={id} className="field w-full" value={v ?? ""} onChange={(e) => onChange(e.target.value)}>
        {(f.options || []).map((o) => <option key={optVal(o)} value={optVal(o)}>{optLab(o)}</option>)}
      </select>); break;
    case "bool": return (
      <label className="flex items-center gap-2 text-[13px] cursor-pointer min-h-[32px]">
        <input type="checkbox" checked={!!v} onChange={(e) => onChange(e.target.checked)} /> {f.label}
        {f.help && <span className="text-[11.5px] text-faint">· {f.help}</span>}
      </label>);
    case "multi": {
      const cur = new Set(Array.isArray(v) ? v : []);
      return (
        <fieldset className="border-0 p-0 m-0">
          <legend className="text-[12px] text-muted mb-1">{f.label}</legend>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {(f.options || []).map((o) => (
              <label key={optVal(o)} className="flex items-center gap-1.5 text-[12.5px] cursor-pointer">
                <input type="checkbox" checked={cur.has(optVal(o))} onChange={(e) => {
                  const n = new Set(cur); if (e.target.checked) n.add(optVal(o)); else n.delete(optVal(o));
                  onChange((f.options || []).map(optVal).filter((x) => n.has(x))); }} /> {optLab(o)}
              </label>
            ))}
          </div>
        </fieldset>);
    }
    default: ctl = <input id={id} className="field w-full" value={v ?? ""} onChange={(e) => onChange(e.target.value)} />;
  }
  return <div>{lab}{ctl}{f.help && <div className="text-[11.5px] text-faint mt-1">{f.help}</div>}</div>;
}

export default function ConfigPanel({ open, onClose, def, cfg, onCfg, title, onTitle, channel, onChannel }) {
  const tid = useId();
  if (!def) return null;
  return (
    <Dialog open={open} onClose={onClose} title={`Cấu hình · ${def.title}`} variant="drawer">
      <div className="p-3 grid gap-3">
        <div>
          <label htmlFor={tid} className="block text-[12px] text-muted mb-1">Tiêu đề (để trống = mặc định)</label>
          <input id={tid} className="field w-full" value={title || ""} placeholder={def.title} maxLength={60} onChange={(e) => onTitle(e.target.value)} />
        </div>
        {def.linkable && (
          <fieldset className="border-0 p-0 m-0">
            <legend className="text-[12px] text-muted mb-1">Kênh liên kết mã</legend>
            <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Kênh liên kết">
              <button type="button" role="radio" aria-checked={!channel} className={cn("btn !h-7", !channel && "!border-accent")} onClick={() => onChannel(null)}>Không</button>
              {CHANNELS.map((c) => (
                <button key={c.id} type="button" role="radio" aria-checked={channel === c.id} onClick={() => onChannel(c.id)}
                  className={cn("btn !h-7 !px-2", channel === c.id && "!border-accent")}><ChannelDot channel={c.id} />{c.label}</button>
              ))}
            </div>
            <div className="text-[11.5px] text-faint mt-1">Đổi mã ở một widget thì mọi widget cùng màu trong workspace đổi theo.</div>
          </fieldset>
        )}
        {def.configSchema.map((f) => <Field key={f.key} f={f} value={cfg[f.key]} onChange={(v) => onCfg({ [f.key]: v })} />)}
        {!def.configSchema.length && !def.linkable && <p className="m-0 text-muted text-[12.5px]">Widget này không có tuỳ chọn riêng.</p>}
        <button type="button" className="btn justify-center mt-2" onClick={onClose}>Xong</button>
      </div>
    </Dialog>
  );
}
