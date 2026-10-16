// Danh mục widget TỰ PHÁT HIỆN: mỗi `widgets/<tên>.jsx` xuất default component + `export const meta`. Không cần sửa file nào khác.
// meta: { id, title, icon, group, desc?, defaultSize:{w,h}, minSize?:{w,h}, linkable?, configSchema? } — xem docs/WIDGETS.md.
import { lazy } from "react";
import { Box } from "lucide-react";
import widgetMeta from "virtual:ts-meta/widgets";

const loaders = import.meta.glob("../widgets/*.jsx");

export const WIDGETS = {};
for (const [p, load] of Object.entries(loaders)) {
  const name = p.replace(/^.*\//, "").replace(/\.jsx$/, "");
  const m = widgetMeta[name];
  if (!m) { console.warn(`[terminal] widget ${name}.jsx thiếu "export const meta" nên bị bỏ qua`); continue; }
  const id = m.id || name;
  if (WIDGETS[id]) console.warn(`[terminal] meta.id "${id}" trùng giữa ${WIDGETS[id].file}.jsx và ${name}.jsx — bản sau ghi đè`);
  WIDGETS[id] = {
    id, file: name, title: m.title || id, icon: m.icon || Box, group: m.group || "Khác", desc: m.desc || "",
    defaultSize: m.defaultSize || { w: 8, h: 8 }, minSize: m.minSize || { w: 3, h: 3 },
    linkable: !!m.linkable, bare: !!m.bare, configSchema: m.configSchema || [], Comp: lazy(load),
  };
}
export const WIDGET_LIST = Object.values(WIDGETS).sort((a, b) => a.group.localeCompare(b.group, "vi") || a.title.localeCompare(b.title, "vi"));
export const WIDGET_GROUPS = [...new Set(WIDGET_LIST.map((w) => w.group))];

/** Giá trị cấu hình đầy đủ = mặc định trong schema + phần người dùng đã đổi. */
export function resolveConfig(def, stored) {
  const out = {};
  for (const f of def?.configSchema || []) if (f.default !== undefined) out[f.key] = f.default;
  return { ...out, ...(stored || {}) };
}
