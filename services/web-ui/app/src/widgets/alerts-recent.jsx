import { Bell } from "lucide-react";
import { Async, Chip } from "../components/ui";
import { useAlerts } from "../lib/queries";
import { clean, dateTime } from "../lib/format";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "alerts-recent", title: "Cảnh báo gần nhất", icon: Bell, group: "Vận hành", desc: "Các cảnh báo mới nhất, lọc theo mức độ.",
  defaultSize: { w: 8, h: 8 }, minSize: { w: 4, h: 4 },
  configSchema: [
    { key: "limit", label: "Số dòng", type: "number", default: 12, min: 3, max: 50 },
    { key: "level", label: "Mức độ", type: "select", default: "", options: [{ value: "", label: "Tất cả" }, { value: "crit", label: "Nghiêm trọng" }, { value: "warn", label: "Cảnh báo" }, { value: "info", label: "Thông tin" }] },
  ],
};

export default function AlertsRecent() {
  const { config } = useWidget();
  const q = useAlerts({ limit: config.limit || 12, level: config.level || undefined });
  return (
    <div className="tm-fill tm-scroll tm-pad">
      <Async q={q} rows={4} empty="Không có cảnh báo nào.">
        {(d) => (
          <ul className="m-0 p-0 list-none divide-y divide-line">
            {d.items.map((a) => (
              <li key={a.id} className="flex items-start gap-2 py-[6px]">
                <Chip tone={a.level === "crit" ? "down" : a.level === "warn" ? "accent" : ""}>{a.level === "crit" ? "Nghiêm trọng" : a.level === "warn" ? "Cảnh báo" : "Thông tin"}</Chip>
                <span className="flex-1 min-w-0 truncate" title={clean(a.body || "")}>{clean(a.title)}</span>
                <span className="text-[11.5px] text-faint shrink-0">{dateTime(a.ts)}</span>
              </li>
            ))}
          </ul>
        )}
      </Async>
    </div>
  );
}
