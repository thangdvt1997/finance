import { useId, useMemo, useState } from "react";
import { Save, Sparkles } from "lucide-react";
import { Dialog } from "../../dialog";
import { toast } from "../../../ux/bus";
import { api, useFleetMut, KIND_VN } from "../../../lib/fleetQueries";
import { Field, ErrLine, GBtn, PRIMARY, RoNote } from "../bits";
import { KINDS_FALLBACK, defaults, fieldsOf, toForm, toParams, validate } from "./schema";

const GRID = { gridTemplateColumns: "repeat(auto-fit, minmax(min(11rem, 100%), 1fr))" };

/** Trình soạn mẫu luật (tạo/sửa). Kiểm tra phía client; lỗi 422 của máy chủ hiển thị nguyên văn. */
export default function RuleEditor({ template, presets, kinds, onClose, onSaved }) {
  const uid = useId();
  const editing = !!template;
  const kindList = kinds?.length ? kinds : KINDS_FALLBACK;
  const [kind, setKind] = useState(template?.kind || "daily_loss");
  const [name, setName] = useState(template?.name || "");
  const [desc, setDesc] = useState(template?.description || "");
  const [form, setForm] = useState(() => (template ? toForm(template.kind, template.params) : defaults("daily_loss")));
  const [touched, setTouched] = useState(false);
  const errs = useMemo(() => validate(kind, form), [kind, form]);
  const nameErr = !name.trim() ? "Bắt buộc nhập tên." : name.trim().length > 80 ? "Tên tối đa 80 ký tự." : "";
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const changeKind = (k) => { setKind(k); setForm(defaults(k)); };
  const applyPreset = (i) => {
    const p = presets?.[Number(i)];
    if (!p) return;
    setKind(p.kind); setForm(toForm(p.kind, p.params)); if (!name.trim()) setName(p.name);
  };
  const save = useFleetMut(
    (body) => (editing ? api.put(`/rules/templates/${template.id}`, body) : api.post("/rules/templates", body)),
    ["tpl", "assign", "compliance"],
    { onSuccess: (r) => { toast({ tone: "ok", title: editing ? "Đã lưu mẫu luật" : "Đã tạo mẫu luật", body: name.trim() }); onSaved?.(r); onClose(); } },
  );
  const submit = (e) => {
    e.preventDefault();
    setTouched(true);
    if (nameErr || Object.keys(errs).length) return;
    save.mutate({ name: name.trim(), kind, params: toParams(kind, form), description: desc.trim() });
  };
  const fields = fieldsOf(kind).filter((f) => !f.showIf || f.showIf(form));
  const invalid = !!nameErr || Object.keys(errs).length > 0;

  return (
    <Dialog open onClose={onClose} title={editing ? `Sửa mẫu luật` : "Tạo mẫu luật"} className="!min-w-0 !max-w-[640px]"
      footer={<>
        <RoNote className="mr-auto" />
        <button type="button" className="btn" onClick={onClose}>Huỷ</button>
        <GBtn type="submit" form={`${uid}-f`} master perm="compliance.read" className={PRIMARY} disabled={save.isPending}><Save size={14} aria-hidden="true" />{save.isPending ? "Đang lưu…" : "Lưu mẫu luật"}</GBtn>
      </>}>
      <form id={`${uid}-f`} onSubmit={submit} noValidate className="p-3 grid gap-3 grid-cols-[minmax(0,1fr)]">
        {!editing && presets?.length > 0 && (
          <Field label={<span className="inline-flex items-center gap-1"><Sparkles size={13} aria-hidden="true" />Mẫu gợi ý</span>} htmlFor={`${uid}-pre`} help="Chọn một mẫu trung tính để điền sẵn các ô bên dưới, rồi chỉnh theo hợp đồng thực tế.">
            <select id={`${uid}-pre`} className="field" defaultValue="" onChange={(e) => { applyPreset(e.target.value); }}>
              <option value="" disabled>— Chọn mẫu gợi ý —</option>
              {kindList.map((k) => (
                <optgroup key={k.kind} label={k.label || KIND_VN[k.kind]}>
                  {presets.map((p, i) => (p.kind === k.kind ? <option key={i} value={i}>{p.name}</option> : null))}
                </optgroup>
              ))}
            </select>
          </Field>
        )}
        <div className="fl-formgrid" style={GRID}>
          <Field label="Tên mẫu" htmlFor={`${uid}-n`} hint="Tên gọi dễ nhớ, hiện trong bảng tuân thủ và sự cố." error={touched ? nameErr : ""}>
            <input id={`${uid}-n`} className="field" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="vd Lỗ ngày 5%" aria-invalid={touched && !!nameErr} autoComplete="off" data-autofocus />
          </Field>
          <Field label="Loại luật" htmlFor={`${uid}-k`} hint="Loại luật quyết định các tham số bên dưới. Không đổi được sau khi tạo; cần loại khác thì tạo mẫu mới." help={editing ? "Không đổi loại khi sửa." : undefined}>
            <select id={`${uid}-k`} className="field" value={kind} disabled={editing} onChange={(e) => changeKind(e.target.value)}>
              {kindList.map((k) => <option key={k.kind} value={k.kind}>{k.label || KIND_VN[k.kind]}</option>)}
            </select>
          </Field>
        </div>
        <fieldset className="fl-formgrid !border-0 !p-0 !m-0 min-w-0" style={GRID}>
          <legend className="fl-sr">Tham số luật</legend>
          {fields.map((f) => {
            const id = `${uid}-${f.key}`;
            const common = { id, className: "field", value: form[f.key] ?? "", onChange: (e) => set(f.key, e.target.value), "aria-invalid": touched && !!errs[f.key] };
            return (
              <Field key={f.key} label={<>{f.label}{f.req ? <span className="text-down" aria-hidden="true"> *</span> : null}</>} htmlFor={id} hint={f.hint} error={touched ? errs[f.key] : ""}
                help={f.unit && f.type !== "sel" ? `Đơn vị: ${f.unit}` : undefined}>
                {f.type === "sel"
                  ? <select {...common}>{f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
                  : f.type === "tz" ? <input {...common} placeholder="UTC, UTC+3, Europe/Prague" autoComplete="off" spellCheck={false} />
                  : <input {...common} inputMode="decimal" className="field num" autoComplete="off" required={!!f.req} />}
              </Field>
            );
          })}
        </fieldset>
        <Field label="Ghi chú" htmlFor={`${uid}-d`} hint="Ghi chú nội bộ (vd hợp đồng/nhà cái áp dụng).">
          <textarea id={`${uid}-d`} className="field" rows={2} maxLength={400} value={desc} onChange={(e) => setDesc(e.target.value)} />
        </Field>
        {touched && invalid && <div role="alert" className="text-[12px] text-down">Còn {Object.keys(errs).length + (nameErr ? 1 : 0)} ô chưa hợp lệ — xem thông báo dưới từng ô.</div>}
        <ErrLine error={save.error} />
      </form>
    </Dialog>
  );
}
