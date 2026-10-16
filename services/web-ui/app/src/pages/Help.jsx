// Trợ giúp: Bắt đầu nhanh · Thuật ngữ (tìm được) · Câu hỏi thường gặp · Ghi chú phiên bản. Liên kết sâu: ?tab=thuat-ngu&term=spread, ?tab=hoi-dap&faq=3.
import { useEffect, useMemo, useRef } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { BookOpen, Compass, HelpCircle, History, Keyboard, Search, Sparkles, LifeBuoy } from "lucide-react";
import { PageHead, Panel, cn } from "../components/ui";
import { EmptyState } from "../components/ux/States";
import { FAQ, GLOSSARY, GLOSSARY_CATS, foldText } from "../ux/glossary";
import { BUILD_TIME, CHANGELOG, VERSION } from "../ux/changelog";
import { useHashQuery } from "../ux/urlstate";
import { appCmd } from "../ux/actions";


export const meta = { path: "tro-giup", label: "Trợ giúp", group: "Tiện ích", icon: LifeBuoy, order: 20, roles: ["master", "client"], keywords: "thuat ngu glossary faq cau hoi huong dan changelog phien ban help" };
const TABS = [["bat-dau", "Bắt đầu", Compass], ["thuat-ngu", "Thuật ngữ", BookOpen], ["hoi-dap", "Câu hỏi thường gặp", HelpCircle], ["phien-ban", "Ghi chú phiên bản", History]];

function Hit({ text, q }) {
  const t = q.trim();
  if (!t) return text;
  const i = foldText(text).indexOf(foldText(t));
  if (i < 0) return text;
  return <>{text.slice(0, i)}<mark className="ux-mark">{text.slice(i, i + t.length)}</mark>{text.slice(i + t.length)}</>;
}

function Start() {
  const steps = [
    ["Tổng quan", "#/tong-quan", "Bức tranh toàn hệ thống: giá, tin, lịch, tài khoản trong một màn hình."],
    ["Thị trường", "#/thi-truong", "Biểu đồ nến, chỉ báo, công cụ vẽ. Chọn mã ở danh sách bên trái, khung ở thanh trên biểu đồ."],
    ["Cảnh báo", "#/canh-bao", "Tạo quy tắc theo giá, chỉ báo, tin, margin. Thông báo về chuông, điện thoại (ntfy) hoặc Telegram."],
    ["Danh sách theo dõi", "#/danh-sach", "Gom các mã bạn quan tâm thành nhóm; băng giá trên cùng lấy theo nhóm đang chọn."],
    ["Cài đặt", "#/cai-dat", "Giao diện, màu tăng/giảm, múi giờ, âm báo, thông báo trình duyệt."],
  ];
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Panel title="Năm việc nên làm đầu tiên" icon={Sparkles}>
        <ol className="ux-prose m-0 pl-5 grid gap-2">
          {steps.map(([t, h, d]) => <li key={h}><a href={h}><b>{t}</b></a><span className="text-muted"> — {d}</span></li>)}
        </ol>
        <div className="flex flex-wrap gap-2 mt-3">
          <button type="button" className="btn" onClick={() => appCmd("tour")}><Compass size={13} aria-hidden="true" /> Xem lại hướng dẫn làm quen</button>
          <button type="button" className="btn" onClick={() => appCmd("help")}><Keyboard size={13} aria-hidden="true" /> Bảng phím tắt</button>
        </div>
      </Panel>
      <Panel title="Cách đọc giao diện" icon={HelpCircle}>
        <div className="ux-prose text-[13px]">
          <p><b>Huy hiệu “N phút trước”</b>: độ tươi dữ liệu. Xanh mới, vàng chậm, đỏ cũ, xám (trăng) là thị trường nghỉ.</p>
          <p><b>Chấm “Trực tiếp”</b>: kênh dữ liệu thời gian thực. Mất kết nối thì có banner và giao diện tự nối lại.</p>
          <p><b>Chỉ-đọc</b>: hệ thống chỉ xem số liệu tài khoản MT4/MT5, không đặt/sửa/đóng lệnh.</p>
          <p><b>Từ gạch chấm</b>: rê chuột hoặc Tab tới để xem giải thích; nhấn Enter để ghim. Tra cứu đầy đủ ở tab Thuật ngữ.</p>
          <p><b>Ctrl K</b>: tìm nhanh mọi thứ; gõ <kbd className="ux-kbd">&gt;</kbd> cho lệnh, <kbd className="ux-kbd">?</kbd> cho thuật ngữ.</p>
          <p className="text-muted">Dữ liệu chỉ để tham khảo, không phải khuyến nghị đầu tư.</p>
        </div>
      </Panel>
    </div>
  );
}

function Glossary({ q }) {
  const [cat, setCat] = useHashQuery("cat", "");
  const [term] = useHashQuery("term", "");
  const ref = useRef(null);
  const list = useMemo(() => {
    const t = foldText(q.trim());
    return GLOSSARY.filter((g) => (!cat || g.cat === cat) && (!t || foldText(`${g.term} ${(g.aka || []).join(" ")} ${g.short} ${g.long}`).includes(t)));
  }, [q, cat]);
  useEffect(() => { if (term) document.getElementById(`g-${term}`)?.scrollIntoView({ block: "center" }); }, [term, list.length]);
  return (
    <div className="grid gap-3" ref={ref}>
      <div className="flex flex-wrap gap-1" role="group" aria-label="Lọc theo nhóm">
        <button type="button" className={cn("ux-chip", !cat && "on")} aria-pressed={!cat} onClick={() => setCat("")}>Tất cả ({GLOSSARY.length})</button>
        {Object.entries(GLOSSARY_CATS).map(([k, l]) => <button key={k} type="button" className={cn("ux-chip", cat === k && "on")} aria-pressed={cat === k} onClick={() => setCat(k)}>{l}</button>)}
      </div>
      {list.length === 0 ? <EmptyState icon={Search} title="Không có thuật ngữ khớp" hint="Thử từ khoá ngắn hơn (ví dụ “margin”, “rsi”) hoặc bỏ lọc nhóm." /> : (
        <dl className="m-0 grid gap-2 md:grid-cols-2">
          {list.map((g) => (
            <div key={g.id} id={`g-${g.id}`} className={cn("rounded-md border bg-panel2 p-3 grid gap-1 content-start", term === g.id ? "border-accent" : "border-line")}>
              <dt className="font-semibold"><Hit text={g.term} q={q} /> <span className="text-[11px] text-faint font-normal">· {GLOSSARY_CATS[g.cat]}</span></dt>
              <dd className="m-0 text-[13px]">{g.short}</dd>
              {g.formula && <dd className="m-0"><code className="num text-[12px] text-fg bg-panel px-2 py-[2px] rounded border border-line inline-block">{g.formula}</code></dd>}
              <dd className="m-0 text-[12.5px] text-muted">{g.long}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function Faq({ q }) {
  const [open] = useHashQuery("faq", "");
  const list = useMemo(() => { const t = foldText(q.trim()); return FAQ.map((f, i) => ({ f, i })).filter(({ f }) => !t || foldText(`${f.q} ${f.a}`).includes(t)); }, [q]);
  useEffect(() => { if (open !== "") document.getElementById(`faq-${open}`)?.scrollIntoView({ block: "center" }); }, [open]);
  if (!list.length) return <EmptyState icon={Search} title="Không có câu hỏi khớp" hint="Thử từ khoá khác hoặc xem tab Thuật ngữ." />;
  return (
    <div className="grid gap-2 max-w-[90ch]">
      {list.map(({ f, i }) => (
        <details key={i} id={`faq-${i}`} className="ux-details" open={String(i) === open || !!q.trim()}>
          <summary><Hit text={f.q} q={q} /></summary>
          <div><Hit text={f.a} q={q} /></div>
        </details>
      ))}
    </div>
  );
}

function Changelog() {
  return (
    <div className="grid gap-3 max-w-[90ch]">
      <p className="m-0 text-muted text-[12.5px]">Phiên bản đang chạy: <b className="num text-fg">{VERSION}</b>{BUILD_TIME ? <> · dựng lúc <span className="num">{new Date(BUILD_TIME).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}</span> (giờ VN)</> : null}</p>
      {CHANGELOG.map((c) => (
        <Panel key={c.v} title={`v${c.v} — ${c.title}`} right={<span className="text-[12px] text-muted">{c.date}</span>}>
          <ul className="m-0 pl-5 grid gap-1 text-[13px]">{c.items.map((x, i) => <li key={i}>{x}</li>)}</ul>
        </Panel>
      ))}
    </div>
  );
}

export default function Help() {
  const [tab, setTab] = useHashQuery("tab", "bat-dau");
  const [term] = useHashQuery("term", "");
  const [faq] = useHashQuery("faq", "");
  const [q, setQ] = useHashQuery("q", "");
  const cur = term && tab === "bat-dau" ? "thuat-ngu" : faq !== "" && tab === "bat-dau" ? "hoi-dap" : tab;
  return (
    <>
      <PageHead title="Trợ giúp" sub="Hướng dẫn nhanh, tra cứu thuật ngữ giao dịch, câu hỏi thường gặp và ghi chú phiên bản."
        right={<><label className="sr-only" htmlFor="help-q">Tìm trong trợ giúp</label><div className="relative"><Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true" /><input id="help-q" className="field !pl-7 w-[min(18rem,100%)]" type="search" placeholder="Tìm: margin, drawdown, cảnh báo…" value={q} onChange={(e) => { setQ(e.target.value); if (e.target.value && (cur === "bat-dau" || cur === "phien-ban")) setTab("thuat-ngu"); }} autoComplete="off" /></div></>} />
      <Tabs.Root value={cur} onValueChange={setTab} className="flex flex-col gap-3">
        <Tabs.List className="flex gap-1 overflow-x-auto shrink-0" aria-label="Mục trợ giúp">
          <div className="seg">{TABS.map(([v, l, Ic]) => <Tabs.Trigger key={v} value={v}><span className="inline-flex items-center gap-1"><Ic size={13} aria-hidden="true" />{l}</span></Tabs.Trigger>)}</div>
        </Tabs.List>
        <Tabs.Content value="bat-dau" className="outline-none"><Start /></Tabs.Content>
        <Tabs.Content value="thuat-ngu" className="outline-none"><Glossary q={q} /></Tabs.Content>
        <Tabs.Content value="hoi-dap" className="outline-none"><Faq q={q} /></Tabs.Content>
        <Tabs.Content value="phien-ban" className="outline-none"><Changelog /></Tabs.Content>
      </Tabs.Root>
    </>
  );
}
