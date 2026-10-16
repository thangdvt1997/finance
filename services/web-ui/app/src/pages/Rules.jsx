import { useState } from "react";
import { Gauge, Info, ListChecks, Link2, ShieldCheck } from "lucide-react";
import { PageHead } from "../components/ui";
import { useHashQuery } from "../ux/urlstate";
import { useRuleAssignments, useRulePresets, useRuleTemplates, usePerm, ROLE_VN } from "../lib/fleetQueries";
import { Banner, Pill, RoNote } from "../components/fleet/bits";
import { DISCLAIMER_DEFAULT } from "../components/fleet/rules/schema";
import CompliancePanel from "../components/fleet/rules/CompliancePanel";
import TemplatesPanel from "../components/fleet/rules/TemplatesPanel";
import AssignmentsPanel from "../components/fleet/rules/AssignmentsPanel";

export const meta = { path: "luat", label: "Luật & tuân thủ", group: "Quản trị đội", icon: ShieldCheck, roles: ["master", "analyst"], perm: "compliance.read", order: 30, keywords: "luat tuan thu prop firm drawdown lo ngay margin level compliance rules" };

const TABS = [
  { id: "tuan-thu", label: "Tuân thủ toàn đội", icon: Gauge },
  { id: "mau", label: "Mẫu luật", icon: ListChecks },
  { id: "gan", label: "Gán luật", icon: Link2 },
];

/** Trang "Luật & tuân thủ": #/luat?tab=tuan-thu|mau|gan  (bộ lọc: tt, nhom, tag, luat). Chỉ-đọc về giao dịch — không có đặt lệnh. */
export default function Rules() {
  const p = usePerm();
  const [tab, setTab] = useHashQuery("tab", "tuan-thu");
  const presets = useRulePresets();
  const tpl = useRuleTemplates();
  const asg = useRuleAssignments();
  const [assignTpl, setAssignTpl] = useState(null);
  const disclaimer = presets.data?.disclaimer || DISCLAIMER_DEFAULT;
  const readOnly = !p.isMaster;
  const cur = TABS.some((t) => t.id === tab) ? tab : "tuan-thu";

  return (
    <div className="fl-page" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
      <PageHead title="Luật & tuân thủ" sub="Theo dõi mức dùng hạn mức của từng tài khoản theo luật bạn cấu hình (lỗ ngày, drawdown, margin level…). Công cụ giám sát — không can thiệp tài khoản."
        right={<><RoNote />{readOnly && <Pill tone="info" icon={Info} title="Soạn/gán/xoá luật chỉ dành cho master">Chỉ xem · {ROLE_VN[p.role] || p.role}</Pill>}</>} />

      <Banner tone="warn" title="Lưu ý về luật nhà cái / prop firm" className="fl-sticky-banner">{disclaimer}</Banner>

      <div role="tablist" aria-label="Mục Luật & tuân thủ" className="fl-tabs" onKeyDown={(e) => { const i = TABS.findIndex((t) => t.id === cur); const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0; if (!d) return; e.preventDefault(); const n = TABS[(i + d + TABS.length) % TABS.length].id; setTab(n); setTimeout(() => document.getElementById(`rl-tab-${n}`)?.focus(), 0); }}>
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`rl-tab-${t.id}`} aria-controls="rl-panel" aria-selected={cur === t.id} tabIndex={cur === t.id ? 0 : -1} onClick={() => setTab(t.id)}>
            <t.icon size={14} aria-hidden="true" />{t.label}
            {t.id === "mau" && tpl.data?.items ? <span className="num text-muted">{tpl.data.items.length}</span> : null}
            {t.id === "gan" && asg.data?.items ? <span className="num text-muted">{asg.data.items.length}</span> : null}
          </button>
        ))}
      </div>

      <div id="rl-panel" role="tabpanel" aria-labelledby={`rl-tab-${cur}`} className="grid gap-3 min-w-0 grid-cols-[minmax(0,1fr)]">
      {cur === "tuan-thu" && <CompliancePanel />}
      {cur === "mau" && <TemplatesPanel tpl={tpl} presets={presets.data} onAssign={(t) => { setAssignTpl(t); setTab("gan"); }} />}
      {cur === "gan" && <AssignmentsPanel asg={asg} tpl={tpl} presetTpl={assignTpl} onCloseAssign={() => setAssignTpl(null)} />}
      </div>
    </div>
  );
}
