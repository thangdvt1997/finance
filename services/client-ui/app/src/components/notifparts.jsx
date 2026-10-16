import { Chip, cn } from "./ui";
import { clean, dateTime, dateY, rel, vnDayKey } from "../lib/format";
import { t } from "../lib/i18n";

/** Công tắc bật/tắt (vùng chạm 56x44). */
export function Switch({ on, onChange, label, disabled }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled} onClick={() => onChange(!on)} className="ibtn !w-[56px] shrink-0 disabled:opacity-50" style={{ border: 0 }}>
      <span className="relative inline-block w-[44px] h-[26px] rounded-full motion-safe:transition-colors" style={{ background: on ? "var(--up)" : "var(--line2)" }}>
        <span className="absolute top-[3px] w-[20px] h-[20px] rounded-full bg-white motion-safe:transition-all" style={{ left: on ? 21 : 3 }} />
      </span>
    </button>
  );
}

export const levelLabel = (l) => (l === "crit" || l === "danger" ? t("Nghiêm trọng") : l === "warn" ? t("Cảnh báo") : t("Thông tin"));
export const levelTone = (l) => (l === "crit" || l === "danger" ? "down" : l === "warn" ? "accent" : "info");

/** Nhãn ngày cho nhóm: Hôm nay / Hôm qua / dd/mm/yyyy (giờ VN). */
export function dayLabel(ts, now = Date.now()) {
  const k = vnDayKey(ts);
  if (k === vnDayKey(now)) return t("Hôm nay");
  if (k === vnDayKey(now - 86400e3)) return t("Hôm qua");
  return dateY(ts);
}

/** Nhóm danh sách (đã sắp theo thời gian giảm dần) theo ngày VN. -> [{key,label,items}] */
export function groupByDay(items, now = Date.now()) {
  const out = [];
  for (const x of items) {
    const k = vnDayKey(x.ts);
    let g = out[out.length - 1];
    if (!g || g.key !== k) { g = { key: k, label: dayLabel(x.ts, now), items: [] }; out.push(g); }
    g.items.push(x);
  }
  return out;
}

/** Liên kết nội bộ an toàn từ chuỗi máy chủ: chỉ nhận đường dẫn băm dạng /abc. Trả null nếu lạ. */
export function safeLink(link) {
  if (typeof link !== "string") return null;
  let s = link.trim();
  const i = s.indexOf("#");
  if (i >= 0) s = s.slice(i + 1);
  return /^\/[a-z0-9\-_/]*(\?[a-zA-Z0-9=&_.%-]*)?$/i.test(s) ? `#${s}` : null;
}

/** Lịch sử kích hoạt quy tắc cảnh báo (từ máy chủ). */
export function RuleEventsList({ items }) {
  return (
    <ul className="list-none m-0 p-0 grid">
      {items.map((e, i) => (
        <li key={e.id ?? i} className="py-2.5 border-b border-line last:border-0 grid gap-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <b className="text-[13.5px] break-words min-w-0">{clean(e.rule_name)}</b>
            <Chip tone={levelTone(e.level)}>{levelLabel(e.level)}</Chip>
            <span className="text-[12px] text-faint ml-auto num" title={dateTime(e.ts)}>{rel(e.ts)}</span>
          </div>
          <div className="text-[13px] break-words">{clean(e.title)}</div>
          {e.body && <div className={cn("text-[12.5px] text-muted whitespace-pre-line break-words")}>{clean(e.body)}</div>}
        </li>
      ))}
    </ul>
  );
}
