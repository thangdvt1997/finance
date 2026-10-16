// Lệnh Ctrl-K của Terminal (đăng ký qua registerCommandProvider của ux/commands): chuyển workspace, thêm widget, khoá bố cục, trình chiếu.
import { LayoutGrid, Lock, PlusSquare, Presentation, LayoutTemplate } from "lucide-react";
import { registerCommandProvider, score } from "../ux/commands";
import { addWidget, addWorkspace, getTerminal, setActive, setKiosk, setLocked } from "./store";
import { WIDGET_LIST } from "./registry";

let done = false;
const toTerminal = () => { if (!/^#\/terminal/.test(location.hash)) location.hash = "#/terminal"; };

export function registerTerminalCommands() {
  if (done) return;
  done = true;
  registerCommandProvider((q) => {
    const term = (q || "").trim();
    if (term.length < 2) return [];
    const st = getTerminal();
    const items = [];
    for (const id of st.o) {
      const n = st.w[id].n;
      items.push({ id: `tm-ws-${id}`, group: "Terminal", label: `Mở workspace “${n}”`, hint: id === st.a ? "đang mở" : "Terminal", icon: LayoutGrid, kw: `workspace terminal ${n}`, run: () => { toTerminal(); setActive(id); } });
    }
    for (const w of WIDGET_LIST) {
      items.push({ id: `tm-w-${w.id}`, group: "Terminal", label: `Thêm widget: ${w.title}`, hint: "vào workspace hiện tại", icon: PlusSquare, kw: `them widget terminal ${w.title} ${w.group} ${w.desc}`, run: () => { toTerminal(); addWidget(getTerminal().a, w.id); } });
    }
    items.push({ id: "tm-new", group: "Terminal", label: "Terminal: tạo workspace trống", hint: "", icon: LayoutTemplate, kw: "workspace moi tao terminal", run: () => { toTerminal(); addWorkspace("blank"); } });
    items.push({ id: "tm-lock", group: "Terminal", label: "Terminal: khoá / mở khoá bố cục", hint: "", icon: Lock, kw: "khoa mo khoa bo cuc layout lock terminal", run: () => { const s = getTerminal(); setLocked(s.a, !s.w[s.a].l); } });
    items.push({ id: "tm-kiosk", group: "Terminal", label: "Terminal: toàn màn hình / trình chiếu", hint: "Esc để thoát", icon: Presentation, kw: "kiosk trinh chieu toan man hinh wall display terminal", run: () => { toTerminal(); setTimeout(() => setKiosk(true), 150); } });
    return items.filter((it) => score(`${it.label} ${it.kw}`, term) >= 0).sort((a, b) => score(`${b.label} ${b.kw}`, term) - score(`${a.label} ${a.kw}`, term)).slice(0, 8);
  });
}
