// Thanh lọc sự cố. Trạng thái nằm trên URL hash (useHashQuery) nên chia sẻ được liên kết.
import { useEffect, useState } from "react";
import { Layers, List, Search, SlidersHorizontal, X } from "lucide-react";
import { Seg } from "../../ui";
import { useHashQuery } from "../../../ux/urlstate";
import { KIND_OPTS, SEV } from "./model";

export function useIncFilters() {
  const [gr, setGr] = useHashQuery("gr", "");
  const [sv, setSv] = useHashQuery("sv", "");
  const [as, setAs] = useHashQuery("as", "");
  const [kd, setKd] = useHashQuery("kd", "");
  const [ac, setAc] = useHashQuery("ac", "");
  const [q, setQ] = useHashQuery("q", "");
  const [gop, setGop] = useHashQuery("gop", "");
  return { gr, sv, as, kd, ac, q, gop, set: { gr: setGr, sv: setSv, as: setAs, kd: setKd, ac: setAc, q: setQ, gop: setGop } };
}

function AccountInput({ value, onCommit }) {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  const commit = () => { const t = v.trim(); if (t !== value && (!t || /^[\w.:-]{1,64}$/.test(t))) onCommit(t); };
  return <input className="field num !w-[9.5rem]" value={v} onChange={(e) => setV(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") commit(); }} placeholder="Mã tài khoản…" aria-label="Lọc theo mã tài khoản (Enter để áp dụng)" />;
}

export default function Filters({ f, groups, assignees, meId, found, total, onClear }) {
  const gs = groups.data?.items || [];
  const as = assignees.data?.items || [];
  const [more, setMore] = useState(false);
  const active = [f.gr, f.sv, f.as, f.kd, f.ac, f.q].filter(Boolean).length;
  const chips = [];
  if (f.gr) chips.push(["gr", `Nhóm: ${gs.find((g) => g.id === f.gr)?.name || "…"}`]);
  if (f.sv) chips.push(["sv", `Mức: ${SEV[f.sv]?.label || f.sv}`]);
  if (f.as) chips.push(["as", `Phụ trách: ${f.as === "me" ? "tôi" : f.as === "none" ? "chưa giao" : as.find((u) => u.user_id === f.as)?.name || "…"}`]);
  if (f.kd) chips.push(["kd", `Loại: ${KIND_OPTS.find((o) => o.value === f.kd)?.label || f.kd}`]);
  if (f.ac) chips.push(["ac", `Tài khoản: ${f.ac}`]);
  return (
    <div className="grid gap-2" role="search" aria-label="Lọc sự cố">
      <div className="fl-bar-tools">
        <div className="fl-search">
          <Search size={14} aria-hidden="true" />
          <input className="field" type="search" value={f.q} onChange={(e) => f.set.q(e.target.value)} placeholder="Tìm tiêu đề, tài khoản, người phụ trách…" aria-label="Tìm sự cố" />
        </div>
        <button type="button" className="btn sm:!hidden" aria-expanded={more} aria-controls="inc-fsel" onClick={() => setMore(!more)}><SlidersHorizontal size={13} aria-hidden="true" />Bộ lọc{active ? ` (${active})` : ""}</button>
        <div id="inc-fsel" className="inc-fsel" data-open={more ? "1" : undefined}>
        <select className="field" aria-label="Lọc theo nhóm" value={f.gr} onChange={(e) => f.set.gr(e.target.value)}>
          <option value="">Mọi nhóm</option>
          {gs.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
        </select>
        <select className="field" aria-label="Lọc theo mức" value={f.sv} onChange={(e) => f.set.sv(e.target.value)}>
          <option value="">Mọi mức</option>
          {Object.entries(SEV).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <select className="field" aria-label="Lọc theo người phụ trách" value={f.as} onChange={(e) => f.set.as(e.target.value)}>
          <option value="">Mọi người phụ trách</option>
          <option value="me">Của tôi</option>
          <option value="none">Chưa giao</option>
          {as.filter((u) => u.user_id !== meId).map((u) => <option key={u.user_id} value={u.user_id}>{u.name}</option>)}
        </select>
        <select className="field" aria-label="Lọc theo loại sự cố" value={f.kd} onChange={(e) => f.set.kd(e.target.value)}>
          {KIND_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <AccountInput value={f.ac} onCommit={f.set.ac} />
        </div>
        <Seg label="Cách hiển thị" value={f.gop ? "gop" : "ds"} onChange={(v) => f.set.gop(v === "gop" ? "1" : "")}
          options={[{ value: "ds", label: <span className="inline-flex items-center gap-1"><List size={12} aria-hidden="true" />Danh sách</span> }, { value: "gop", label: <span className="inline-flex items-center gap-1"><Layers size={12} aria-hidden="true" />Gộp theo lỗi</span> }]} />
      </div>
      <div className="fl-active-filters">
        <span className="fl-count" aria-live="polite">{found === total ? `${total} sự cố` : `${found}/${total} sự cố khớp`}</span>
        {chips.map(([k, label]) => <span key={k} className="fl-fchip">{label}<button type="button" aria-label={`Bỏ lọc ${label}`} onClick={() => f.set[k]("")}><X size={11} aria-hidden="true" /></button></span>)}
        {(active > 0) && <button type="button" className="ux-link text-[12px]" onClick={onClear}>Xoá bộ lọc</button>}
      </div>
    </div>
  );
}
