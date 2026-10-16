// "AI Training Class": chuyên gia ngồi DẠY AI một kịch bản qua chat (phòng, streaming SSE, nhãn ví dụ, biểu đồ chọn khoảng nến, sổ tay phương pháp).
// CHỈ nghiên cứu/paper: không có nút/đường đặt lệnh. Hợp đồng API: docs/handoff/AI_CLASSROOM_API.md.
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, BookOpen, ChartCandlestick, Download, FlaskConical, ListChecks, MessageSquare, Pin, Plus, Search, UserPlus, UserRound, Users, X, ClipboardList, Brain } from "lucide-react";
import { Chip, Seg, cn } from "../ui";
import { EmptyState } from "../ux/States";
import { fetchMe } from "../../lib/clientsApi";
import { cget, cpost, fileB64, streamMessage } from "./classApi";
import { ClassCtx, hhmm } from "./ctx";
import Bubble, { ActionCard } from "./MessageView";
import Markdown from "./Markdown";
import Composer from "./Composer";
import ExampleChart from "./ExampleChart";
import { Notebook, PinsPanel } from "./SidePanels";
import { ExamplesTab, TestTab, useLabels } from "./LessonTabs";
import { briefText } from "./templates";
import TopBar from "./TopBar";
import ProfileCanvas, { EXAMPLES, useCanvas } from "./ProfileCanvas";
import { Slot } from "./slots";
import { useRoomManager } from "./RoomsTrash";
import "./classroom.css";

// Chip hành động nhanh: nhãn tự nhiên (không lộ lệnh); [khoá, vi, en, [mô tả vi, en], lệnh nội bộ gửi AI | "chart"]
const QUICK = [
  ["test", "Chạy thử", "Test it", ["Backtest trung thực, cần xác nhận", "Honest backtest, needs confirmation"], "/test"],
  ["scan", "Tìm ví dụ", "Find examples", ["Quét lịch sử tìm những lần giống kịch bản", "Scan history for look-alike cases"], "/quet"],
  ["variant", "Biến thể", "Variants", ["Biến thể, đối lập, phản ví dụ", "Variants, opposites, counter-examples"], "/bien-the"],
  ["mirror", "Phía mua", "Buy side", ["Phiên bản đối xứng", "Mirrored version"], "/doi-xung"],
  ["compare", "So với mua-giữ", "Vs buy-and-hold", ["So sánh với mua-giữ", "Compare with buy-and-hold"], "/so-sanh"],
  ["sum", "Tóm lại", "Sum up", ["AI nói lại điều đã hiểu", "The AI restates what it understood"], "/tom-tat"],
  ["draw", "Vẽ lên biểu đồ", "Draw on chart", ["Chọn vùng nến / đánh dấu", "Pick candle range / mark"], "chart"],
];
const FINAL = new Set(["done", "failed", "cancelled"]);
const PHASE = { intake: ["Giao kịch bản", "Intake"], interview: ["Hỏi sâu", "Interview"], review: ["Rà soát", "Review"] };
const lsGet = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* bỏ */ } };
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random()));

function RoomList({ q, rid, onPick, onCreated, t, llm, mgr }) {
  const [title, setTitle] = useState(""), [name, setName] = useState(""), [err, setErr] = useState(null), [busy, setBusy] = useState(false), [open, setOpen] = useState(false);
  const items = q.data?.items || [];
  const create = async (e) => {
    e.preventDefault(); if (title.trim().length < 3) return;
    setBusy(true); setErr(null);
    try { const r = await cpost("/rooms", { title: title.trim().slice(0, 80), ...(name.trim() ? { display_name: name.trim().slice(0, 60) } : {}) }); setTitle(""); setOpen(false); onCreated(r); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <div className="cr-rooms">
      <div className="flex items-center gap-2 p-2 border-b border-line">
        <b className="text-[12.5px]">{t("Phòng học", "Classrooms")}</b>
        <button type="button" className="btn cr-sm ml-auto" onClick={() => setOpen(!open)} aria-expanded={open}><Plus size={13} aria-hidden="true" />{t("Phòng mới", "New room")}</button>
      </div>
      {open && (
        <form className="grid gap-1 p-2 border-b border-line" onSubmit={create}>
      {mgr?.toolbar}
          <input className="cr-inp" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={80} placeholder={t("Tên kịch bản/chủ đề (3-80 ký tự)", "Scenario/topic name (3-80 chars)")} aria-label={t("Tên phòng", "Room name")} required minLength={3} />
          <input className="cr-inp" value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder={t("Tên hiển thị của bạn (tuỳ chọn)", "Your display name (optional)")} aria-label={t("Tên hiển thị", "Display name")} />
          <button type="submit" className="btn cr-sm" disabled={busy || title.trim().length < 3}>{t("Tạo phòng", "Create room")}</button>
          {err && <p role="alert" className="m-0 text-[12px] text-down">{err}</p>}
        </form>
      )}
      {q.isError && <p className="m-0 p-2 text-[12.5px] text-muted">{q.error?.status === 404 || q.error?.status >= 502 ? t("Dịch vụ AI Training Class chưa sẵn sàng. Trang sẽ tự tải lại.", "The Classroom service is not ready. The page reloads automatically.") : q.error?.message}</p>}
      {q.isPending && <p className="m-0 p-2 text-[12.5px] text-muted">{t("Đang tải…", "Loading…")}</p>}
      {!q.isPending && !q.isError && !items.length && <p className="m-0 p-2 text-[12.5px] text-muted">{t("Chưa có phòng nào. Tạo phòng đầu tiên: mỗi kịch bản/chủ đề một phòng.", "No rooms yet. Create the first one: one room per scenario/topic.")}</p>}
      <ul className="m-0 p-0 list-none cr-roomlist">
        {items.map((r) => {
          const ph = PHASE[r.phase];
          return (
            <li key={r.id} className="cr-roomrow">{mgr?.rowCheck(r)}<button type="button" className={cn("cr-room", r.id === rid && "on")} aria-current={r.id === rid} onClick={() => (mgr?.selecting ? mgr.toggle?.(r.id) : onPick(r.id))}>
              <span className="flex items-center gap-1 min-w-0"><b className="truncate text-[13px]">{r.title}</b>{r.profile_version != null && <Chip>v{r.profile_version}</Chip>}</span>
              <span className="text-[11.5px] text-muted truncate">{r.last_message ? `${r.last_message.author?.name || ""}: ${String(r.last_message.text || "").replace(/\s+/g, " ").slice(0, 70)}` : t("Chưa có tin nhắn", "No messages yet")}</span>
              <span className="flex items-center gap-1 text-[11px] text-faint"><Users size={11} aria-hidden="true" />{(r.members || []).length}{ph && <span>· {t(ph[0], ph[1])}</span>}<span className="ml-auto">{hhmm(r.updated_at)}</span></span>
            </button>{mgr?.rowTrash(r)}</li>
          );
        })}
      </ul>
    </div>
  );
}

function Invite({ rid, t, onDone }) {
  const [u, setU] = useState(""), [n, setN] = useState(""), [role, setRole] = useState("expert"), [err, setErr] = useState(null), [busy, setBusy] = useState(false);
  const ok = /^[A-Za-z0-9_.:@-]{1,64}$/.test(u);
  const go = async (e) => { e.preventDefault(); setBusy(true); setErr(null); try { await cpost(`/rooms/${encodeURIComponent(rid)}/members`, { user_id: u.trim(), name: (n.trim() || u.trim()).slice(0, 60), role }); setU(""); setN(""); onDone(); } catch (x) { setErr(x.message); } finally { setBusy(false); } };
  return (
    <form className="cr-card grid gap-1" onSubmit={go} aria-label={t("Mời người vào phòng", "Invite to room")}>
      <div className="grid gap-1 sm:grid-cols-2"><input className="cr-inp" value={u} onChange={(e) => setU(e.target.value)} placeholder={t("Mã đăng nhập của chuyên gia", "Expert login id")} aria-label="user id" /><input className="cr-inp" value={n} onChange={(e) => setN(e.target.value)} placeholder={t("Tên hiển thị", "Display name")} maxLength={60} aria-label={t("Tên hiển thị", "Display name")} /></div>
      <div className="flex gap-1 items-center flex-wrap"><select className="cr-inp cr-sel" value={role} onChange={(e) => setRole(e.target.value)} aria-label={t("Vai trò", "Role")}><option value="expert">{t("Chuyên gia", "Expert")}</option><option value="master">Master</option></select><button type="submit" className="btn cr-sm" disabled={busy || !ok}>{t("Mời", "Invite")}</button><span className="text-[11.5px] text-muted">{t("Chuyên gia chỉ dạy + chạy test paper; không mở test khoá, không đụng cấu hình.", "Experts can only teach + run paper tests; no locked test, no system config.")}</span></div>
      {err && <p role="alert" className="m-0 text-[12px] text-down">{err}</p>}
    </form>
  );
}

export default function Classroom({ lang = "vi" }) {
  const t = useCallback((vi, en) => (lang === "en" ? en : vi), [lang]);
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe, staleTime: 300_000, retry: false }).data || {};
  const isMaster = me.role === "master";
  const [rid, setRid] = useState(() => lsGet("cr-room", "")), [view, setView] = useState("chat"), [side, setSide] = useState("profile");
  const [panel, setPanel] = useState(null), [tourOpen, setTourOpen] = useState(false), [focusKey, setFocusKey] = useState(null), [speed, setSpeed] = useState(0);
  const [colL, setColL] = useState(() => lsGet("cr-colL", matchMedia("(min-width: 1180px)").matches ? "1" : "0") === "1"), [colR, setColR] = useState(() => lsGet("cr-colR", "1") === "1");
  const sheetBack = useRef(null), sheetClose = useRef(null);
  const [streaming, setStreaming] = useState(false), [live, setLive] = useState(null), [sendErr, setSendErr] = useState(null), [notice, setNotice] = useState(null);
  const [older, setOlder] = useState([]), [search, setSearch] = useState(""), [showSearch, setShowSearch] = useState(false), [invite, setInvite] = useState(false);
  const [ask, setAsk] = useState(() => lsGet("cr-mode", "ai") === "ai"), [acts, setActs] = useState({}), [actBusy, setActBusy] = useState(false), [chartSel, setChartSel] = useState({ symbol: "EURUSD", tf: "H1" });
  const rootRef = useRef(null), firstView = useRef(true), abort = useRef(null), box = useRef(null), stick = useRef(true), comp = useRef(null), sRef = useRef(null);
  const [showDown, setShowDown] = useState(false), [memCards, setMemCards] = useState([]), [memFocus, setMemFocus] = useState(null);

  const rooms = useQuery({ queryKey: ["cls", "rooms"], queryFn: ({ signal }) => cget("/rooms", {}, signal), refetchInterval: 12000, retry: (n, e) => n < 1 && !(e?.status >= 400 && e.status < 500) });
  const rs = rooms.data?.items || [];
  useEffect(() => { if (rooms.data && rid && !rs.some((r) => r.id === rid)) { setRid(rs[0]?.id || ""); } else if (rooms.data && !rid && rs.length) setRid(rs[0].id); }, [rooms.data]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (rid) lsSet("cr-room", rid); setOlder([]); setLive(null); setActs({}); setSendErr(null); setNotice(null); setSearch(""); setShowSearch(false); stick.current = true; }, [rid]);
  const mgr = useRoomManager({ t, rooms: rs, rid, isMaster });

  const room = useQuery({ queryKey: ["cls", rid, "room"], enabled: !!rid, queryFn: ({ signal }) => cget(`/rooms/${encodeURIComponent(rid)}`, { limit: 50 }, signal), refetchInterval: streaming ? false : 4000, retry: false });
  const sq = useQuery({ queryKey: ["cls", rid, "search", search], enabled: !!rid && search.trim().length >= 2, queryFn: ({ signal }) => cget(`/rooms/${encodeURIComponent(rid)}`, { q: search.trim().slice(0, 80), limit: 50 }, signal) });
  const d = room.data, r0 = d?.room || rs.find((r) => r.id === rid);
  const merged = useMemo(() => { const m = new Map(); for (const x of [...older, ...(d?.messages || [])]) m.set(x.id, x); return [...m.values()].sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0)); }, [older, d?.messages]);
  const scans = useMemo(() => merged.filter((m) => m.kind === "scan" && m.data?.examples?.length), [merged]);
  const pinned = d?.pinned || merged.filter((m) => m.pinned);
  const inv = () => { qc.invalidateQueries({ queryKey: ["cls", rid] }); qc.invalidateQueries({ queryKey: ["cls", "rooms"] }); };

  useEffect(() => { if (firstView.current) { firstView.current = false; return; } if (matchMedia("(max-width: 1179px)").matches) rootRef.current?.scrollIntoView({ block: "start" }); }, [view]);
  // --- cuộn ---
  const toBottom = () => { const e = box.current; if (e) { e.scrollTop = e.scrollHeight; stick.current = true; setShowDown(false); } };
  useEffect(() => { if (stick.current) toBottom(); else setShowDown(true); }, [merged.length, live?.text, live?.final]);
  const onScroll = () => { const e = box.current; if (!e) return; const near = e.scrollHeight - e.scrollTop - e.clientHeight < 80; stick.current = near; setShowDown(!near); };
  const loadOlder = async () => {
    const minSeq = merged[0]?.seq; if (minSeq == null) return;
    try { const x = await cget(`/rooms/${encodeURIComponent(rid)}`, { limit: 50, before: minSeq }); setOlder((o) => [...(x.messages || []), ...o]); } catch (e) { setSendErr(e.message); }
  };

  // --- gửi tin (SSE) ---
  const send = async (text) => {
    if (!rid || streaming) return;
    const ac = new AbortController(); abort.current = ac; setStreaming(true); setSendErr(null); stick.current = true;
    setLive({ user: { id: "local-u", seq: 1e12, kind: "text", author: { user_id: me.user_id, name: me.display_name || me.user_id, role: me.role }, text, created_at: new Date().toISOString() }, text: "", got: false });
    let t0 = 0, nch = 0;
    try {
      await streamMessage(rid, text, {
        user: (e) => setLive((l) => l && { ...l, user: e.message }),
        delta: (e) => { if (!t0) t0 = performance.now(); nch += (e.text || "").length; setLive((l) => l && { ...l, text: l.text + (e.text || ""), got: true }); },
        turn: (e) => { setLive((l) => l && { ...l, final: e.message }); if (e.turn?.questions) setNotice(null); },
        action: (e) => e.action && setActs((a) => ({ ...a, [e.action.id]: e.action })),
        error: (e) => setSendErr(e.detail || t("AI gặp lỗi, thử lại.", "The AI hit an error, retry.")),
      }, ac.signal, uid());
    } catch (e) { setSendErr(e.message); setLive(null); setStreaming(false); throw e; }
    if (t0 && nch > 20) { const dt = (performance.now() - t0) / 1000; if (dt > 0.2) setSpeed(nch / dt); }
    try { await qc.refetchQueries({ queryKey: ["cls", rid, "room"] }); } catch { /* bỏ */ }
    setLive(null); setStreaming(false); qc.invalidateQueries({ queryKey: ["cls", "rooms"] }); qc.invalidateQueries({ queryKey: ["cls", rid, "profile"] }); qc.invalidateQueries({ queryKey: ["cls", rid, "labels"] }); qc.invalidateQueries({ queryKey: ["cls", rid, "canvas"] });
  };
  const stop = () => { abort.current?.abort(); setStreaming(false); setLive(null); inv(); };

  const model = useCanvas(rid, lang, send);
  const lab = useLabels(rid);
  const progress = useMemo(() => {
    const ans = model.profile?.answers && typeof model.profile.answers === "object" ? Object.values(model.profile.answers).reduce((n, a) => n + (Array.isArray(a) ? a.filter((x) => x && !x.skipped && String(x.text || "").trim()).length : 0), 0) : 0;
    const userMsgs = merged.filter((m) => m.author?.role !== "ai" && m.author?.user_id !== "ai" && (m.kind || "text") === "text" && !String(m.text || "").trim().startsWith("/")).length;
    return { rooms: rs.length, answers: Math.max(ans, userMsgs), labels: lab.items.length, versions: (model.versions || []).length, tests: merged.filter((m) => m.kind === "result_card").length };
  }, [model.profile, model.versions, merged, rs.length, lab.items.length]);
  const pre = useRef(null);
  // Lần đầu vào Lớp học: tự mở tour 5 bước (khoá cr-tour-done); đóng/ bỏ qua thì không hiện lại, nút "Tham quan" mở lại.
  useEffect(() => { if (rid && room.isSuccess && lsGet("cr-tour-done", "") !== "1") { const h = setTimeout(() => setTourOpen(true), 600); return () => clearTimeout(h); } return undefined; }, [rid, room.isSuccess]);
  const fill = (s) => { if (!rid) { pre.current = s; setNotice(t("Hãy tạo hoặc chọn một phòng; nội dung sẽ được điền sẵn vào ô nhập.", "Create or pick a room first; the text will be pre-filled in the input.")); setPanel(null); return; } setView("chat"); setPanel(null); setTimeout(() => comp.current?.insert(s), 30); };
  useEffect(() => { if (rid && room.isSuccess && pre.current) { const s = pre.current; pre.current = null; setView("chat"); setTimeout(() => comp.current?.insert(s), 60); } }, [rid, room.isSuccess]); // eslint-disable-line react-hooks/exhaustive-deps
  const openSide = (v) => { setSide(v); setView("side"); setColR(true); };
  const toggleL = () => setColL((v) => { lsSet("cr-colL", v ? "0" : "1"); return !v; });
  const toggleR = () => setColR((v) => { lsSet("cr-colR", v ? "0" : "1"); return !v; });
  const hint = (row) => { openSide("profile"); setFocusKey(row.key); setTimeout(() => setFocusKey(null), 2500); };
  const openPanel = (p) => { sheetBack.current = document.activeElement; setPanel(p); };
  const closePanel = () => { setPanel(null); setTimeout(() => sheetBack.current?.focus?.(), 0); };
  const openMem = (id) => { setMemFocus(id); setSide("memory"); setView("side"); setColR(true); };
  useEffect(() => { if (panel) sheetClose.current?.focus(); }, [panel]);

  // --- hành động nền ---
  const serverActs = d?.pending_actions || [];
  const actList = useMemo(() => { const m = new Map(); for (const a of Object.values(acts)) m.set(a.id, a); for (const a of serverActs) m.set(a.id, a); return [...m.values()].filter((a) => !FINAL.has(a.status) || a.status === "failed").slice(-4); }, [acts, serverActs]);
  useEffect(() => {
    const live_ = Object.values(acts).filter((a) => !FINAL.has(a.status) && a.status !== "needs_confirm"); if (!live_.length || !rid) return undefined;
    const h = setInterval(async () => { for (const a of live_) { try { const n = await cget(`/rooms/${encodeURIComponent(rid)}/actions/${encodeURIComponent(a.id)}`); setActs((x) => ({ ...x, [a.id]: n })); if (FINAL.has(n.status)) inv(); } catch { /* bỏ */ } } }, 3000);
    return () => clearInterval(h);
  }, [acts, rid]); // eslint-disable-line react-hooks/exhaustive-deps
  const confirmAct = async (a) => {
    setActBusy(true);
    try { const n = await cpost(`/rooms/${encodeURIComponent(rid)}/actions/${encodeURIComponent(a.id)}/confirm`, {}); setActs((x) => ({ ...x, [a.id]: n.action || n })); inv(); } catch (e) { setSendErr(e.message); } finally { setActBusy(false); }
  };

  // --- đính kèm / biểu đồ ---
  const upload = async (files) => {
    const warn = [];
    for (const x of files) {
      const body = x.kind === "note" ? { kind: x.kind, name: x.file.name, text: (await x.file.text()).slice(0, 4000) } : { kind: x.kind, name: x.file.name, data_b64: await fileB64(x.file) };   // backend: image/yaml/csv/pdf đều qua data_b64 (chỉ note dùng text)
      if (x.caption.trim()) body.caption = x.caption.trim();
      const r = await cpost(`/rooms/${encodeURIComponent(rid)}/attachments`, body);
      (r.warnings || []).forEach((w) => warn.push(String(w)));
    }
    setNotice(warn.length ? warn.join(" · ") : null); inv();
  };
  const submitChart = async ({ symbol, tf, annotations, note }) => {
    setNotice(null); let n = 0;
    try {
      for (const a of annotations) {
        if (a.kind === "khoang") {
          await cpost(`/rooms/${encodeURIComponent(rid)}/attachments`, { kind: "note", name: "khoang-nen.txt", text: `Khoảng nến ví dụ: ${symbol} ${tf} từ ${a.t1} đến ${a.t2}.${note ? ` Ghi chú: ${note}` : ""}` });
        } else {
          const pts = [{ ts: a.t1, price: a.p1 }, ...(a.t2 ? [{ ts: a.t2, price: a.p2 }] : [])];
          await cpost(`/rooms/${encodeURIComponent(rid)}/actions`, { command: "ve", params: { kind: a.kind, note: note || "", symbol, tf, from_ts: a.t1, to_ts: a.t2 || a.t1, points: pts } });
        }
        n++;
      }
      setNotice(t(`Đã đính ${n} đánh dấu vào phòng.`, `Attached ${n} marks to the room.`)); inv(); setView("chat");
    } catch (e) { setNotice(e.message); }
  };
  const pin = async (m) => { try { await cpost(`/rooms/${encodeURIComponent(rid)}/pins`, { message_id: m.id, pinned: !m.pinned }); inv(); } catch (e) { setSendErr(e.message); } };

  // --- phím tắt ---
  useEffect(() => {
    const h = (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") { e.preventDefault(); e.stopImmediatePropagation(); setShowSearch(true); setView("chat"); setTimeout(() => sRef.current?.focus(), 30); }
      else if ((e.ctrlKey || e.metaKey) && e.key === "/") { e.preventDefault(); setView("chat"); comp.current?.focus(); }
      else if (e.altKey && /^[1-6]$/.test(e.key)) { e.preventDefault(); setSide(["profile", "label", "test", "chart", "notebook", "pins"][+e.key - 1]); setView("side"); setColR(true); }
      else if (e.altKey && e.key.toLowerCase() === "l") { e.preventDefault(); toggleL(); }
      else if (e.altKey && e.key.toLowerCase() === "r") { e.preventDefault(); toggleR(); }
      else if (e.key === "Escape" && panel) { closePanel(); }
      else if (e.key === "Escape" && showSearch) { setShowSearch(false); setSearch(""); }
    };
    addEventListener("keydown", h, true); return () => removeEventListener("keydown", h, true);
  }, [showSearch, panel]); // eslint-disable-line react-hooks/exhaustive-deps

  const ctx = useMemo(() => ({ lang, t, me, rid, isMaster }), [lang, t, me, rid, isMaster]);
  const st = d?.state || {}, ph = PHASE[st.phase || r0?.phase];
  const searching = search.trim().length >= 2;
  const shown = searching ? sq.data?.messages || [] : merged;
  const missing = st.missing_required || [];
  const SIDE = [["profile", UserRound, t("Hồ sơ", "Profile")], ["label", ListChecks, t("Ví dụ", "Examples")], ["test", FlaskConical, t("Test", "Test")], ["chart", ChartCandlestick, t("Biểu đồ", "Chart")], ["notebook", BookOpen, t("Sổ tay", "Notebook")], ["pins", Pin, t("Ghim", "Pins")], ["memory", Brain, t("Bộ nhớ", "Memory")]];
  const NAV = [["chat", MessageSquare, t("Chat", "Chat")], ["profile", UserRound, t("Hồ sơ", "Profile")], ["label", ListChecks, t("Ví dụ", "Examples")], ["test", FlaskConical, t("Test", "Test")]];
  const navOn = (k) => (k === "chat" ? view === "chat" : view === "side" && side === k);
  const slotProps = { lang, rid, profile: model.profile, canvas: model.canvas, onSend: send, onFill: fill, model, progress };

  const PANELS = { guide: ["GuidePanel", t("Cách dạy hiệu quả", "How to teach well")], demo: ["DemoPlayer", t("Buổi học mẫu (minh hoạ)", "Sample lesson (illustrative)")], templates: ["TemplatePicker", t("Mẫu khởi tạo kịch bản", "Scenario templates")] };
  const sheet = panel && PANELS[panel];

  return (
    <ClassCtx.Provider value={ctx}>
      <div className={cn("cr", !colL && "no-l", !colR && "no-r")} data-view={view} ref={rootRef}>
        <TopBar t={t} title={r0?.title} version={d?.room?.profile_version ?? r0?.profile_version ?? model.profile?.version} clarity={model.canvas.clarity} hasRoom={!!rid}
          onHint={hint} onSave={() => send("/luu").catch(() => {})} onTest={() => send("/test").catch(() => {})} onExport={() => openSide("notebook")}
          onDemo={() => openPanel("demo")} onGuide={() => openPanel("guide")} onTemplates={() => openPanel("templates")} onTour={() => { try { localStorage.removeItem("cr-tour-done"); } catch { /* bỏ */ } setTourOpen(true); }}
          llm={rooms.data?.llm} speed={speed} streaming={streaming} busy={streaming || !!room.isError} left={colL} right={colR} onToggleLeft={toggleL} onToggleRight={toggleR} onRooms={() => setView("rooms")} />

        <aside className={cn("cr-col cr-c-rooms panel", view === "rooms" && "show")} aria-label={t("Danh sách phòng", "Rooms")} data-tour="rooms">
          <div className="cr-rooms-wrap"><RoomList q={rooms} rid={rid} t={t} mgr={mgr} onPick={(id) => { setRid(id); setView("chat"); }} onCreated={(r) => { qc.invalidateQueries({ queryKey: ["cls", "rooms"] }); setRid(r.id); setView("chat"); }} /></div>
          <div className="cr-checklist"><Slot name="Checklist" quiet lang={lang} rid={rid} profile={model.profile} canvas={model.canvas} progress={progress} onSend={send} onFill={fill} /></div>
        </aside>

        <section className={cn("cr-col cr-c-chat panel", view === "chat" && "show")} aria-label={t("Khung chat", "Chat")} data-tour="chat">
          {!rid ? <div className="p-4 grid gap-3 justify-items-start"><EmptyState compact title={t("Chọn hoặc tạo một phòng", "Pick or create a room")} hint={t("Mỗi kịch bản/chủ đề một phòng. Giao kịch bản cho AI bằng 3 câu: mã, khung, hình dạng, vào/ra thế nào.", "One room per scenario/topic. Hand the scenario to the AI in 3 sentences: symbol, timeframe, shape, entry/exit.")} /><button type="button" className="btn" onClick={() => openPanel("templates")}>{t("Chọn từ mẫu", "Start from a template")}</button></div> : (<>
            <header className="cr-head">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">{ph && <Chip tone="info">{t(ph[0], ph[1])}{st.total > 0 && st.idx != null ? ` · ${t("bước", "step")} ${Math.min(st.idx + 1, st.total)}/${st.total}` : ""}</Chip>}<div className="flex gap-1 flex-wrap">{(r0?.members || []).map((m) => <span key={m.user_id} className="cr-member" title={m.role}>{m.name}<i>{m.role === "master" ? "Master" : t("Chuyên gia", "Expert")}</i></span>)}</div></div>
              </div>
              <div className="flex gap-1 items-center shrink-0 flex-wrap justify-end">
                <button type="button" className="btn ghost cr-sm" aria-pressed={showSearch} onClick={() => { setShowSearch(!showSearch); setTimeout(() => sRef.current?.focus(), 30); }} aria-label={t("Tìm trong phòng (Ctrl+K)", "Search room (Ctrl+K)")}><Search size={14} /></button>
                <button type="button" className="btn ghost cr-sm" aria-pressed={invite} onClick={() => setInvite(!invite)} aria-label={t("Mời", "Invite")}><UserPlus size={14} /><span className="hidden sm:inline">{t("Mời", "Invite")}</span></button>
                <a className="btn ghost cr-sm" href={`/api/v1/ai-trading/class/rooms/${encodeURIComponent(rid)}/minutes.md`} download aria-label={t("Tải biên bản", "Download minutes")}><Download size={14} /><span className="hidden sm:inline">{t("Biên bản", "Minutes")}</span></a>
              </div>
            </header>
                {mgr.headerBtn(r0)}
            {st.total > 0 && <div className="cr-prog" role="progressbar" aria-valuemin={0} aria-valuemax={st.total} aria-valuenow={Math.min(st.idx ?? 0, st.total)} aria-label={t("Tiến độ checklist", "Checklist progress")}><i style={{ width: `${Math.min(100, ((st.idx ?? 0) / st.total) * 100)}%` }} /></div>}
            {invite && <div className="p-2 border-b border-line"><Invite rid={rid} t={t} onDone={() => { setInvite(false); inv(); }} /></div>}
            {showSearch && (
              <div className="p-2 border-b border-line flex gap-1"><input ref={sRef} className="cr-inp flex-1" value={search} maxLength={80} onChange={(e) => setSearch(e.target.value)} placeholder={t("Tìm trong phòng (≥2 ký tự)…", "Search the room (≥2 chars)…")} aria-label={t("Tìm kiếm", "Search")} /><button type="button" className="btn ghost cr-sm" onClick={() => { setShowSearch(false); setSearch(""); }} aria-label={t("Đóng tìm kiếm", "Close search")}><X size={14} /></button></div>
            )}
            <div className="cr-msgwrap">
            <div className="cr-msgs cr-print" ref={box} onScroll={onScroll} role="log" aria-live="polite" aria-label={t("Hội thoại", "Conversation")}>
              {room.isError && <p className="m-3 text-[13px] text-muted">{room.error?.status === 404 ? t("Không tìm thấy phòng (hoặc bạn không phải thành viên).", "Room not found (or you are not a member).") : room.error?.message}</p>}
              {searching && <p className="m-0 px-3 py-2 text-[12px] text-muted">{sq.isFetching ? t("Đang tìm…", "Searching…") : `${shown.length} ${t("kết quả cho", "results for")} "${search.trim()}"`}</p>}
              {!searching && d?.has_more && <div className="text-center py-2"><button type="button" className="btn ghost cr-sm" onClick={loadOlder}>{t("Tải tin cũ hơn", "Load older")}</button></div>}
              {!searching && room.isSuccess && !merged.length && !live && (
                <div className="cr-start" role="note">
                  <ClipboardList size={22} aria-hidden="true" className="text-muted" />
                  <h3 className="m-0 text-[15px] font-semibold">{t("Hãy mô tả kịch bản bằng 3 câu", "Describe the scenario in 3 sentences")}</h3>
                  <p className="m-0 text-[13px] text-muted">{t("Nêu mã và khung, hình dạng giá, và vào/ra thế nào. Càng cụ thể (có số) thì Độ rõ ý tưởng càng tăng. AI sẽ hỏi từng cụm nhỏ và điền Hồ sơ kịch bản bên phải để bạn sửa.", "Give the symbol and timeframe, the price shape, and how to enter/exit. The more specific (with numbers), the higher the Idea clarity. The AI asks small groups of questions and fills the Scenario profile on the right for you to correct.")}</p>
                  <p className="m-0 text-[12px] text-muted">{t("Bấm một ví dụ mở đầu để điền vào ô nhập (rồi sửa):", "Pick an example opener to fill the input (then edit it):")}</p>
                  <ul className="m-0 p-0 list-none grid gap-1 w-full">{EXAMPLES.map(([vi, en], i) => <li key={i}><button type="button" className="cr-chip cr-chip-wide" onClick={() => fill(lang === "en" ? en : vi)}>{lang === "en" ? en : vi}</button></li>)}</ul>
                  <div className="flex gap-2 flex-wrap"><button type="button" className="btn" onClick={() => openPanel("templates")}>{t("Chọn từ mẫu", "Start from a template")}</button><button type="button" className="btn ghost" onClick={() => openPanel("demo")}>{t("Xem buổi học mẫu", "Watch the sample lesson")}</button></div>
                </div>
              )}
              {shown.map((m) => <Fragment key={m.id}><Bubble msg={m} mine={m.author?.user_id === me.user_id} onSend={send} onFill={fill} onPin={pin} onChanged={inv} goLabel={() => openSide("label")} openChart={(a) => { setChartSel({ symbol: a.symbol, tf: a.tf }); openSide("chart"); }} /><MemoryUsed items={m.data?.memory_used || m.memory_used} lang={lang} onOpen={openMem} /></Fragment>)}
              {!searching && live && (<>
                {live.user && !merged.some((m) => m.id === live.user.id) && <Bubble msg={live.user} mine />}
                {live.final ? <><Bubble msg={live.final} onSend={send} onFill={fill} onPin={pin} onChanged={inv} /><MemoryUsed items={live.mem} lang={lang} onOpen={openMem} /></> : (
                  <article className="cr-msg ai" aria-busy="true"><header className="cr-msg-h"><b>{t("AI học trò", "AI student")}</b><Chip>AI</Chip></header>{live.got ? <Markdown text={live.text} /> : <span className="cr-typing" role="status" aria-label={t("AI đang trả lời", "AI is replying")}><i /><i /><i /></span>}</article>
                )}
              </>)}
            </div>
            {showDown && <button type="button" className="cr-down btn" onClick={toBottom} aria-label={t("Xuống tin mới nhất", "Jump to latest")}><ArrowDown size={14} /></button>}
            </div>
            <div className="cr-bottom" data-tour="composer">
              {sendErr && <p role="alert" className="m-0 px-3 py-1 text-[12.5px] text-down">{sendErr}</p>}
              {notice && <p role="status" className="m-0 px-3 py-1 text-[12.5px] text-muted">{notice}</p>}
              {actList.length > 0 && <div className="px-2 pt-2 grid gap-1">{actList.map((a) => <ActionCard key={a.id} a={a} onConfirm={confirmAct} busy={actBusy} />)}</div>}
              {!searching && memCards.length > 0 && <MemoryCards cards={memCards} lang={lang} onChanged={() => qc.invalidateQueries({ queryKey: ["mem"] })} onOpenConflict={() => openMem(null)} />}
              <div className="px-2 pt-2 flex items-center gap-2 flex-wrap">
                <Seg label={t("Chế độ", "Mode")} value={ask ? "ai" : "me"} onChange={(v) => { setAsk(v === "ai"); lsSet("cr-mode", v); }} options={[{ value: "ai", label: t("AI hỏi tôi", "AI asks me") }, { value: "me", label: t("Tôi hỏi AI", "I ask the AI") }]} />
                {ask && missing.length > 0 && <span className="text-[11.5px] text-muted">{t("Còn thiếu (bắt buộc)", "Still missing (required)")}: {missing.slice(0, 4).join(", ")}</span>}
                {ask && streaming === false && merged.length > 0 && <span className="flex gap-1 ml-auto"><button type="button" className="cr-chip" onClick={() => send("đúng")}>{t("Đúng", "Correct")}</button><button type="button" className="cr-chip" onClick={() => send("bỏ qua")}>{t("Bỏ qua", "Skip")}</button></span>}
              </div>
              <Composer ref={comp} chips={d?.chips} streaming={streaming} ask={ask} disabled={!!room.isError} onSend={send} onStop={stop} onUpload={upload} onChart={() => openSide("chart")} onUi={(u) => (u === "notebook" ? openSide("notebook") : u === "templates" ? openPanel("templates") : u === "rooms" ? setColL(true) : null)} />
              <div className="cr-cmds" role="group" aria-label={t("Lệnh nhanh", "Quick commands")}>
                {QUICK.map(([k, vi, en, tip, go]) => <button key={k} type="button" className="cr-chip cr-cmd" title={t(tip[0], tip[1])} disabled={streaming || !!room.isError} onClick={() => (go === "chart" ? openSide("chart") : send(go).catch(() => {}))}>{t(vi, en)}</button>)}
                <span className="cr-keys">Ctrl+/ {t("ô nhập", "input")} · Alt+1..6 {t("bảng phải", "right panel")} · Alt+L/R {t("thu gọn cột", "collapse")} · {t("Đ/S/G gắn nhãn ví dụ", "R/W/C label examples")}</span>
              </div>
              <p className="cr-disc m-0 px-3 pb-2 text-[11.5px] text-muted">{t("Chỉ nghiên cứu/paper: không có lệnh đặt lệnh. AI có thể sai; kết quả test không có edge là bình thường.", "Research/paper only: no order path. The AI can be wrong; a no-edge test result is normal.")}</p>
            </div>
          </>)}
        </section>

        <aside className={cn("cr-col cr-c-side panel", view === "side" && "show")} aria-label={t("Bảng bên", "Side panel")}>
          <div className="cr-sidetabs" role="tablist" aria-label={t("Bảng bên", "Side panel")}>
            {SIDE.map(([v, Ic, l], i) => <button key={v} type="button" role="tab" aria-selected={side === v} className={cn("cr-tab", side === v && "on")} onClick={() => setSide(v)} title={`Alt+${i + 1}`}><Ic size={14} aria-hidden="true" />{l}{v === "pins" && pinned.length > 0 ? ` (${pinned.length})` : ""}</button>)}
          </div>
          <div className="cr-sidebody">
            {!rid ? <p className="m-0 text-[13px] text-muted">{t("Chọn một phòng.", "Pick a room.")}</p>
              : side === "profile" ? <ProfileCanvas lang={lang} rid={rid} canvas={model.canvas} model={model} onSend={send} onFill={fill} focusKey={focusKey} />
              : side === "label" ? <ExamplesTab lang={lang} rid={rid} scans={scans} labels={lab.items} onSend={send} />
              : side === "test" ? <TestTab lang={lang} rid={rid} messages={merged} role={me.role} onSend={send} onEdit={() => fill(t("Tôi muốn sửa kịch bản: ", "I want to change the scenario: "))} />
              : side === "chart" ? <ExampleChart key={`${chartSel.symbol}${chartSel.tf}`} symbol={chartSel.symbol} tf={chartSel.tf} en={lang === "en"} onDone={submitChart} onClose={() => setView("chat")} />
              : side === "notebook" ? <Notebook />
              : <PinsPanel pinned={pinned} onUnpin={pin} />}
          </div>
        </aside>

        <nav className="cr-nav" aria-label={t("Khu vực", "Area")}>
          {NAV.map(([v, Ic, l]) => <button key={v} type="button" className={cn("cr-ntab", navOn(v) && "on")} aria-current={navOn(v) ? "page" : undefined} onClick={() => (v === "chat" ? setView("chat") : openSide(v))}><Ic size={18} aria-hidden="true" /><span>{l}</span></button>)}
              : side === "memory" ? <MemoryPanel lang={lang} rid={rid} focusId={memFocus} />
        </nav>

        {sheet && (
          <div className="cr-sheet-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) closePanel(); }}>
            <div className="cr-sheet" role="dialog" aria-modal="true" aria-label={sheet[1]}>
              <header className="cr-sheet-h"><b className="text-[14px]">{sheet[1]}</b><button ref={sheetClose} type="button" className="cr-iconbtn big ml-auto" onClick={closePanel} aria-label={t("Đóng", "Close")}><X size={16} /></button></header>
              <div className="cr-sheet-b">
                <Slot name={sheet[0]} {...slotProps} onClose={closePanel} onOpen={openPanel} onPick={(tpl) => fill(briefText(tpl, lang))}
                  fallback={<div className="cr-soon" role="status"><p className="m-0 font-semibold text-[13.5px]">{t("Mục này đang được chuẩn bị.", "This section is being prepared.")}</p><p className="m-0 text-[12.5px] text-muted">{t("Trong lúc chờ: mô tả kịch bản bằng 3 câu trong khung chat; AI sẽ hỏi tiếp và điền Hồ sơ kịch bản.", "Meanwhile: describe the scenario in 3 sentences in the chat; the AI asks on and fills the Scenario profile.")}</p><button type="button" className="btn" onClick={closePanel}>{t("Quay lại", "Back")}</button></div>} />
              </div>
            </div>
          </div>
        )}
        {tourOpen && <Slot name="Tour" quiet {...slotProps} onClose={() => setTourOpen(false)} />}
      </div>
    </ClassCtx.Provider>
        {mgr.overlay}
  );
}
