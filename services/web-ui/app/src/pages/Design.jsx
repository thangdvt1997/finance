// Storybook-lite nội bộ (#/design): token màu (kèm tỷ lệ tương phản WCAG), chữ, khoảng cách, bo góc và thư viện thành phần dùng chung.
// Mọi mẫu dùng ĐÚNG component thật của ứng dụng để lệch thiết kế là thấy ngay. Tài liệu: docs/DESIGN_SYSTEM.md.
import { useEffect, useState } from "react";
import { Bell, Layers, Palette, Type } from "lucide-react";
import { Chip, Freshness, ImpactDots, PageHead, Panel, Seg, Skeleton, Sparkline, Stat } from "../components/ui";
import { ChartSkeleton, EmptyState, ErrorState, TableSkeleton } from "../components/ux/States";
import { InfoTip, Term } from "../components/ux/Term";
import { Dialog } from "../components/dialog";
import { toast } from "../ux/bus";
import { useTheme } from "../lib/queries";


export const meta = { path: "design", label: "Design system", group: "Tiện ích", icon: Palette, order: 90, roles: ["master"], keywords: "token mau component storybook thanh phan" };
const TOKENS = [
  ["--bg", "Nền trang", "bg"], ["--panel", "Nền khung", "bg"], ["--panel2", "Nền khung phụ / ô nhập", "bg"], ["--line", "Viền mảnh", "line"], ["--line2", "Viền rõ", "line"],
  ["--fg", "Chữ chính", "text"], ["--muted", "Chữ phụ", "text"], ["--faint", "Chữ mờ (chú thích)", "text"],
  ["--up", "Tăng", "text"], ["--down", "Giảm", "text"], ["--accent", "Nhấn", "text"], ["--info", "Thông tin", "text"], ["--warn", "Cảnh báo", "text"],
  ["--accent-fg", "Chữ trên nền nhấn", "onaccent"], ["--up-bg", "Nền tăng", "tint"], ["--down-bg", "Nền giảm", "tint"], ["--accent-bg", "Nền nhấn nhạt", "tint"],
];
const TYPE = [
  ["text-[19px] font-semibold tracking-tight", "Tiêu đề trang · 19px / 600", "PageHead h1"],
  ["text-[14px] font-semibold", "Tiêu đề hộp thoại · 14px / 600", "Dialog h2"],
  ["text-[13.5px]", "Nội dung · 13.5px / 400", "body"],
  ["text-[12.5px] font-semibold", "Tiêu đề khung, nút, bảng · 12.5px / 650", "panel-h, btn, tbl"],
  ["text-[11.5px] text-muted", "Nhãn / chú thích · 11.5px", "Stat label, th"],
  ["text-[10.5px] uppercase tracking-wider text-faint", "Nhóm điều hướng · 10.5px / 600 hoa", "nav group"],
  ["num text-[15px]", "Số liệu · JetBrains Mono tabular", ".num"],
];

function lum(rgb) { const [r, g, b] = rgb.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; }
function parse(c) {
  const el = document.createElement("canvas").getContext("2d"); el.fillStyle = "#000"; el.fillStyle = c; const v = el.fillStyle;
  if (v.startsWith("#")) return [1, 3, 5].map((i) => parseInt(v.slice(i, i + 2), 16));
  return (v.match(/[\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number);
}
const ratio = (a, b) => { const [x, y] = [lum(parse(a)), lum(parse(b))]; return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };

function Tokens() {
  const [theme] = useTheme();
  const [vals, setVals] = useState({});
  useEffect(() => {
    const cs = getComputedStyle(document.documentElement);
    const v = {}; for (const [k] of TOKENS) v[k] = cs.getPropertyValue(k).trim();
    setVals(v);
  }, [theme]);
  return (
    <div className="ux-ds-grid">
      {TOKENS.map(([k, label, kind]) => {
        const v = vals[k]; let cr = null;
        if (v) { try { cr = kind === "text" ? ratio(v, vals["--panel"]) : kind === "onaccent" ? ratio(v, vals["--accent"]) : null; } catch { cr = null; } }
        return (
          <div key={k} className="ux-ds-tok">
            <i style={{ background: `var(${k})` }} />
            <div><b className="num block">{k}</b><span className="text-muted block">{label}</span><span className="num text-faint block">{v || "…"}</span>
              {cr != null && <span className={`num block ${cr >= 4.5 ? "up" : "down"}`}>{cr.toFixed(1)}:1 {cr >= 4.5 ? "AA đạt" : "chưa đạt AA"}</span>}</div>
          </div>
        );
      })}
    </div>
  );
}

const Demo = ({ title, children, note }) => (
  <section aria-label={title} className="grid gap-2">
    <h3 className="m-0 text-[12.5px] text-muted font-semibold">{title}</h3>
    <div className="ux-ds-demo flex flex-wrap items-start gap-3">{children}</div>
    {note && <p className="m-0 text-[12px] text-faint">{note}</p>}
  </section>
);

export default function Design() {
  const [seg, setSeg] = useState("a");
  const [dlg, setDlg] = useState(false);
  const now = Date.now();
  const err = Object.assign(new Error("Dịch vụ tạm thời không khả dụng."), { status: 503 });
  return (
    <>
      <PageHead title="Design system" sub="Trang nội bộ liệt kê token và thành phần dùng chung. Đổi giao diện/màu nhấn ở Cài đặt để kiểm tra mọi biến thể." right={<a className="btn no-underline" href="#/cai-dat">Cài đặt giao diện</a>} />
      <div className="grid gap-3">
        <Panel title="Màu (token)" icon={Palette}><Tokens /><p className="m-0 mt-3 text-[12px] text-muted">Tỷ lệ tương phản tính trực tiếp trên màu thật của giao diện đang chọn; chữ cần ≥ 4,5:1 (WCAG AA) trên nền khung.</p></Panel>
        <Panel title="Chữ, khoảng cách, bo góc" icon={Type}>
          <div className="grid gap-4 lg:grid-cols-2">
            <ul className="m-0 p-0 list-none grid gap-2">{TYPE.map(([c, t, n]) => <li key={t} className="flex items-baseline gap-3 flex-wrap"><span className={c}>{t}</span><code className="text-[11px] text-faint">{n}</code></li>)}</ul>
            <div className="grid gap-3 text-[12px]">
              <div><b>Khoảng cách</b> (thang 4px): 4 · 8 (gap-2) · 12 (gap-3, khoảng cách giữa khung) · 16 (padding trang) · 24.
                <div className="flex items-end gap-2 mt-2">{[4, 8, 12, 16, 24].map((n) => <span key={n} className="block bg-accent" style={{ width: n, height: n }} title={`${n}px`} />)}</div></div>
              <div><b>Bo góc</b>: 4 (chip nhỏ) · 6 (nút, ô nhập) · 8 (khung) · 10 (menu, tour) · 99 (viên thuốc).
                <div className="flex items-end gap-2 mt-2">{[4, 6, 8, 10, 99].map((n) => <span key={n} className="block border border-line2 bg-panel2" style={{ width: 36, height: 28, borderRadius: n }} title={`${n}px`} />)}</div></div>
              <div><b>Mục tiêu chạm</b> ≥ 44px trên màn cảm ứng (đã áp cho .btn, .field, .seg, menu); <b>focus</b> outline 2px màu nhấn, offset 2px.</div>
            </div>
          </div>
        </Panel>
        <Panel title="Thành phần" icon={Layers}>
          <div className="grid gap-5">
            <Demo title="Nút (.btn), phân đoạn (Seg), ô nhập (.field), chip">
              <button type="button" className="btn">Nút thường</button>
              <button type="button" className="btn ux-btn-primary">Nút chính</button>
              <button type="button" className="btn" disabled>Vô hiệu</button>
              <Seg label="Mẫu" value={seg} onChange={setSeg} options={[{ value: "a", label: "Một" }, { value: "b", label: "Hai" }, { value: "c", label: "Ba" }]} />
              <input className="field" placeholder="Ô nhập (.field)" aria-label="Ô nhập mẫu" />
              <select className="field" aria-label="Ô chọn mẫu"><option>Lựa chọn 1</option><option>Lựa chọn 2</option></select>
              <Chip>mặc định</Chip><Chip tone="up">tăng</Chip><Chip tone="down">giảm</Chip><Chip tone="accent">nhấn</Chip><Chip tone="ro">chỉ-đọc</Chip>
            </Demo>
            <Demo title="Độ tươi dữ liệu (Freshness)" note="Một huy hiệu duy nhất cho mọi nơi: màu + biểu tượng + chữ; xám khi thị trường nghỉ.">
              <Freshness ts={now - 5000} closed={false} /><Freshness ts={now - 90_000} closed={false} /><Freshness ts={now - 900_000} closed={false} /><Freshness ts={now - 3 * 3600e3} closed /><Freshness ts={null} closed={false} />
            </Demo>
            <Demo title="Số liệu (Stat), sparkline, mức tác động">
              <Stat label="Equity" value="12,480.55" sub="USD" /><Stat label="Thay đổi" value="+1.24%" tone="up" /><Stat label="Sụt vốn" value="-3.10%" tone="down" big />
              <Sparkline values={[3, 4, 3.5, 5, 6, 5.5, 7]} /><Sparkline values={[7, 6, 6.5, 5, 4, 4.5, 3]} /><ImpactDots impact="high" /><ImpactDots impact="med" /><ImpactDots impact="low" />
            </Demo>
            <Demo title="Bảng chuẩn (table.tbl)">
              <div className="scroll-x w-full"><table className="tbl" aria-label="Bảng mẫu"><thead><tr><th>Mã</th><th className="r">Giá</th><th className="r">%</th></tr></thead>
                <tbody><tr><td>EURUSD</td><td className="r num">1.08456</td><td className="r num up">+0.12%</td></tr><tr><td>USDJPY</td><td className="r num">149.213</td><td className="r num down">-0.31%</td></tr><tr><td>XAUUSD</td><td className="r num">2,412.50</td><td className="r num flat">0.00%</td></tr></tbody></table></div>
            </Demo>
            <Demo title="Trạng thái tải (skeleton)" note="Giữ đúng kích thước nội dung thật để không giật bố cục.">
              <div className="w-[min(100%,260px)]"><Skeleton rows={4} /></div>
              <div className="w-[min(100%,360px)]"><TableSkeleton rows={4} cols={4} /></div>
              <div className="w-[min(100%,320px)]"><ChartSkeleton height={120} /></div>
            </Demo>
            <Demo title="Trạng thái rỗng và lỗi" note="Rỗng luôn nói vì sao + việc nên làm; lỗi có chẩn đoán theo mã, Thử lại, chi tiết kỹ thuật sao chép được.">
              <div className="w-[min(100%,420px)]"><EmptyState title="Chưa có cảnh báo nào" hint="Tạo quy tắc đầu tiên để được báo khi giá chạm ngưỡng." actions={[{ label: "Tạo cảnh báo", href: "#/canh-bao" }]} /></div>
              <div className="w-[min(100%,460px)]"><ErrorState error={err} what="Danh sách mẫu" onRetry={() => toast({ tone: "info", title: "Đã thử lại (mẫu)", ttl: 1800 })} /></div>
            </Demo>
            <Demo title="Toast, hộp thoại, thuật ngữ">
              {["info", "ok", "warn", "error"].map((t) => <button key={t} type="button" className="btn" onClick={() => toast({ tone: t, title: `Toast ${t}`, body: "Nội dung mẫu của thông báo nhanh.", ttl: 4000 })}><Bell size={13} aria-hidden="true" /> {t}</button>)}
              <button type="button" className="btn" onClick={() => setDlg(true)}>Mở hộp thoại</button>
              <span className="text-[13px]">Tỷ lệ <Term id="margin-level">Margin level</Term> và <Term id="var">VaR</Term> <InfoTip id="drawdown" /></span>
              <kbd className="ux-kbd num">Ctrl</kbd><kbd className="ux-kbd num">K</kbd>
            </Demo>
          </div>
        </Panel>
      </div>
      <Dialog open={dlg} onClose={() => setDlg(false)} title="Hộp thoại mẫu" description="role=dialog, aria-modal, bẫy focus, Esc đóng, trả focus khi đóng." footer={<button type="button" className="btn ux-btn-primary" onClick={() => setDlg(false)}>Đóng</button>}>
        <div className="p-3 text-[13px]">Nội dung hộp thoại. Dùng cho xác nhận, biểu mẫu ngắn, ngăn kéo (variant="drawer").</div>
      </Dialog>
    </>
  );
}
