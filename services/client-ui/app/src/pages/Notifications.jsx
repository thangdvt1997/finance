import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, BellOff, BellRing, Check, CheckCheck, ChevronDown, History, Info, MonitorSmartphone, OctagonAlert, SendHorizontal, Settings2, Trash2 } from "lucide-react";
import { Async, Chip, Notice, PageHead, Panel, Seg, Sheet, Skeleton, cn } from "../components/ui";
import { Switch, RuleEventsList, groupByDay, levelLabel, levelTone, safeLink } from "../components/notifparts";
import { askPermission, markAllRead, markRead, pushSupported, removeNotification, useNotifItems } from "../lib/notifstore";
import { NOTIF_KINDS, currentEndpointHash, deviceName, kindLabel, useClientPrefs, useMarkServerRead, usePushDevices, useRemovePushDevice, useSaveClientPrefs, useServerNotifications } from "../lib/q_notif";
import { useRuleEvents } from "../lib/queries";
import { clean, dateTime, rel } from "../lib/format";
import { useClock } from "../lib/clock";
import { useAuth, accountTitle } from "../lib/auth";
import { usePrefs } from "../lib/prefs";
import { testWebPush } from "../lib/webpush";
import { t } from "../lib/i18n";
import WebPushCard from "../components/pushcard";
import RuleNotifyCard from "../components/rulenotify";

export function PermissionCard() {
  const [perm, setPerm] = useState(typeof Notification === "undefined" ? "unsupported" : Notification.permission);
  if (perm === "unsupported" || !pushSupported()) return <Notice tone="info" title={t("Thiết bị này không hỗ trợ thông báo hệ điều hành")}>{t("Bạn vẫn nhận thông báo trong ứng dụng khi đang mở.")}</Notice>;
  if (perm === "granted") return <Notice tone="up" icon={BellRing} title={t("Thông báo hệ điều hành đã bật")}>{t("Khi ứng dụng mở ở tab nền, cảnh báo sẽ hiện như thông báo của thiết bị. Để nhận cả khi đã đóng hẳn ứng dụng, bật thông báo đẩy bên dưới.")}</Notice>;
  if (perm === "denied") return <Notice tone="warn" icon={BellOff} title={t("Bạn đã chặn thông báo")}>{t("Mở cài đặt trang web của trình duyệt để cho phép lại.")}</Notice>;
  return (
    <Notice tone="info" title={t("Bật thông báo trên thiết bị")} action={<button className="btn sm" onClick={async () => setPerm(await askPermission())}>{t("Bật thông báo")}</button>}>
      {t("Nhận cảnh báo ngay khi ứng dụng đang mở ở tab nền. Không gửi quảng cáo.")}
    </Notice>
  );
}

const SEV = {
  danger: { tone: "down", color: "var(--down)", Icon: OctagonAlert },
  warn: { tone: "accent", color: "var(--accent)", Icon: AlertTriangle },
  info: { tone: "info", color: "var(--info)", Icon: Info },
};
const OPEN = (k) => (k === "rule" ? t("Xem cảnh báo") : k === "limit" ? t("Xem giới hạn") : k === "report" ? t("Xem báo cáo") : k === "briefing" ? t("Đọc bản tin") : k === "support" ? t("Xem hỗ trợ") : t("Xem chi tiết"));

/** Mục thông báo cục bộ (kho trên thiết bị) -> cùng hình dạng với mục máy chủ. */
const fromLocal = (x) => ({ id: `local:${x.id}`, rawId: x.id, local: true, kind: x.kind === "system" ? "system" : "rule", severity: x.level === "crit" ? "danger" : x.level === "warn" ? "warn" : "info", title: x.title, body: x.body, ts: x.ts, read: !!x.read, link: x.kind === "system" ? "/rui-ro" : "/canh-bao" });

function Row({ x, multi, accTitle, onRead, onRemove }) {
  const sv = SEV[x.severity] || SEV.info;
  const href = safeLink(x.link);
  return (
    <li className={cn("px-3.5 py-3 border-b border-line last:border-0 grid gap-1.5", !x.read && "bg-[var(--accent-bg)]")}>
      <div className="flex items-start gap-3">
        <sv.Icon size={18} className="mt-[3px] shrink-0" style={{ color: sv.color }} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <b className={cn("text-[13.5px] break-words min-w-0", x.read && "font-medium")}>{!x.read && <span className="sr-only">{t("Chưa đọc")}: </span>}{clean(x.title)}</b>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 mt-1">
            <Chip>{kindLabel(x.kind)}</Chip>
            <Chip tone={levelTone(x.severity)}>{levelLabel(x.severity)}</Chip>
            {!x.read && <Chip tone="info">{t("Mới")}</Chip>}
            {x.local && <Chip title={t("Sự kiện phát hiện trên thiết bị này")}>{t("Trên thiết bị")}</Chip>}
            {multi && x.account_id && <Chip>{accTitle[x.account_id] || x.account_id}</Chip>}
          </div>
          {x.body && <div className="text-[12.5px] text-muted mt-1 break-words">{clean(x.body)}</div>}
          <div className="text-[11.5px] text-faint mt-0.5 num" title={dateTime(x.ts)}>{rel(x.ts)}</div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 pl-[30px]">
        {href && <a className="btn sm" href={href} onClick={() => !x.read && onRead(x)}>{OPEN(x.kind)}</a>}
        {!x.read && <button type="button" className="btn sm" onClick={() => onRead(x)} aria-label={t("Đánh dấu đã đọc: {title}", { title: clean(x.title) })}><Check size={15} aria-hidden="true" /> {t("Đã đọc")}</button>}
        {x.local && <button type="button" className="btn sm ml-auto" onClick={() => onRemove(x)} aria-label={t("Xoá thông báo {title}", { title: clean(x.title) })}><Trash2 size={15} aria-hidden="true" /> {t("Xoá")}</button>}
      </div>
    </li>
  );
}

function Inbox({ onUnread }) {
  const { accounts } = useAuth();
  const now = useClock();
  const [kind, setKind] = useState("");
  const [only, setOnly] = useState(false);
  const sq = useServerNotifications({ kind, unread: only });
  const local = useNotifItems();
  const markSrv = useMarkServerRead();
  const [msg, setMsg] = useState("");
  const accTitle = useMemo(() => Object.fromEntries(accounts.map((a) => [a.id, accountTitle(a)])), [accounts]);
  const srvItems = useMemo(() => (sq.data?.pages || []).flatMap((p) => p.items || []), [sq.data]);
  const srvUnread = sq.data?.pages?.[0]?.unread ?? 0;
  const locals = useMemo(() => local.map(fromLocal).filter((x) => (!kind || x.kind === kind) && (!only || !x.read)), [local, kind, only]);
  const items = useMemo(() => [...srvItems, ...locals].sort((a, b) => new Date(b.ts) - new Date(a.ts)), [srvItems, locals]);
  const groups = useMemo(() => groupByDay(items, now), [items, now]);
  const unread = srvUnread + local.filter((x) => !x.read).length;
  useEffect(() => { onUnread?.(unread); }, [unread]); // eslint-disable-line react-hooks/exhaustive-deps

  const read = async (x) => {
    setMsg("");
    if (x.local) { markRead(x.rawId); return; }
    try { await markSrv([x.id]); } catch (e) { setMsg(e.message); }
  };
  const readAll = async () => {
    setMsg(""); markAllRead();
    try { await markSrv("all"); } catch (e) { if (!sq.isError) setMsg(e.message); }
  };
  const down = sq.isError;
  return (
    <>
      <div className="min-w-0 max-w-full">
        <Seg value={kind} onChange={setKind} label={t("Lọc theo loại thông báo")} scroll
          options={[{ value: "", label: t("Tất cả") }, ...NOTIF_KINDS.map((k) => ({ value: k, label: kindLabel(k) }))]} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn sm" aria-pressed={only} onClick={() => setOnly((v) => !v)} style={only ? { background: "var(--accent)", color: "var(--accent-fg)", borderColor: "transparent" } : undefined}>{t("Chỉ chưa đọc")}</button>
        <button type="button" className="btn sm ml-auto" onClick={readAll} disabled={!unread}><CheckCheck size={16} aria-hidden="true" /> {unread ? t("Đánh dấu tất cả đã đọc ({n})", { n: unread }) : t("Đánh dấu tất cả đã đọc")}</button>
      </div>
      {msg && <Notice tone="down">{msg}</Notice>}
      {down && <Notice tone="info" title={t("Hộp thư trên máy chủ chưa khả dụng")}>{t("Hiện chỉ hiển thị sự kiện phát hiện trên thiết bị này. Báo cáo, bản tin và giới hạn sẽ xuất hiện ở đây khi máy chủ sẵn sàng.")}</Notice>}
      {sq.isPending ? <Skeleton rows={5} h={52} /> : (
        <Panel title={`${t("Thông báo")}${items.length ? ` (${items.length})` : ""}`} icon={BellRing} pad={false}>
          {items.length === 0 ? (
            <div className="p-4 text-muted text-[13.5px]">
              {only ? t("Không còn thông báo chưa đọc.") : kind ? t("Chưa có thông báo loại này.") : t("Chưa có thông báo.")}{" "}
              <a className="underline" href="#/canh-bao">{t("Tạo cảnh báo")}</a> {t("để nhận thông báo khi giá, margin hoặc kết nối EA thay đổi.")}
            </div>
          ) : groups.map((g) => (
            <section key={g.key} aria-label={g.label}>
              <h3 className="m-0 px-3.5 py-1.5 text-[12px] font-semibold uppercase tracking-wide text-muted bg-panel2 border-b border-line">{g.label}</h3>
              <ul className="list-none m-0 p-0">
                {g.items.map((x) => <Row key={x.id} x={x} multi={accounts.length > 1} accTitle={accTitle} onRead={read} onRemove={(r) => removeNotification(r.rawId)} />)}
              </ul>
            </section>
          ))}
          {sq.hasNextPage && (
            <div className="p-3 border-t border-line">
              <button type="button" className="btn w-full" disabled={sq.isFetchingNextPage} onClick={() => sq.fetchNextPage()}><ChevronDown size={16} aria-hidden="true" /> {sq.isFetchingNextPage ? t("Đang tải...") : t("Xem thêm")}</button>
            </div>
          )}
        </Panel>
      )}
    </>
  );
}

// ---- Cài đặt ----
const PUSH_DEFAULT = { rule: true, limit: true, support: true, report: false, briefing: false };
const KIND_HINT = (k) => (k === "rule" ? t("Khi một cảnh báo bạn đặt kích hoạt") : k === "limit" ? t("Khi bạn gần chạm hoặc chạm giới hạn tự đặt") : k === "report" ? t("Khi báo cáo ngày/tuần/tháng sẵn sàng") : k === "briefing" ? t("Bản tin thị trường buổi sáng và tối") : t("Khi đội hỗ trợ phản hồi yêu cầu của bạn"));
const SETTING_KINDS = ["rule", "limit", "report", "briefing", "support"];

function KindSettings() {
  const cp = useClientPrefs();
  const save = useSaveClientPrefs();
  const { prefs, set } = usePrefs();
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const cur = (data, k, ch) => data?.notif?.[k]?.[ch] ?? (ch === "app" ? true : PUSH_DEFAULT[k] ?? false);
  const apply = (data, k, ch, v) => ({ ...(data || {}), notif: { ...(data?.notif || {}), [k]: { app: cur(data, k, "app"), push: cur(data, k, "push"), [ch]: v } } });
  const toggle = async (k, ch, v) => {
    setBusy(`${k}:${ch}`); setMsg("");
    try {
      try { await save(cp.data.rev, apply(cp.data.data, k, ch, v)); }
      catch (e) {
        if (e.status !== 409) throw e;
        const f = await cp.refetch();            // lệch phiên bản: lấy bản mới nhất rồi áp lại một lần
        await save(f.data.rev, apply(f.data.data, k, ch, v));
      }
    } catch (e) { setMsg(e.message); } finally { setBusy(""); }
  };
  return (
    <Panel title={t("Loại thông báo")} icon={Settings2}>
      <p className="m-0 mb-3 text-[13px] text-muted">{t("Chọn kênh nhận cho từng loại. “Trong ứng dụng” hiện ở chuông và hộp thư; “Đẩy” gửi tới thiết bị đã bật thông báo đẩy, kể cả khi đóng ứng dụng. Nội dung đẩy chỉ là thông báo chung, không có số dư.")}</p>
      {msg && <Notice tone="down" className="mb-3">{msg}</Notice>}
      {cp.isPending ? <Skeleton rows={4} h={44} /> : cp.isError ? (
        <Notice tone="info" title={t("Cài đặt thông báo chưa khả dụng")}>{t("Máy chủ chưa hỗ trợ lưu cài đặt này. Thông báo vẫn được nhận theo mặc định.")}</Notice>
      ) : (
        <ul className="list-none m-0 p-0 grid">
          {SETTING_KINDS.map((k) => (
            <li key={k} className="py-2.5 border-b border-line last:border-0 flex flex-wrap items-center gap-x-4 gap-y-1">
              <div className="min-w-0 flex-1 basis-[12rem]"><div className="font-semibold text-[13.5px]">{kindLabel(k)}</div><div className="text-[12.5px] text-muted">{KIND_HINT(k)}</div></div>
              <div className="flex items-center gap-3">
                <span className="flex items-center text-[12.5px]"><span id={`sw-${k}-app`}>{t("Trong ứng dụng")}</span><Switch on={cur(cp.data.data, k, "app")} disabled={busy === `${k}:app`} onChange={(v) => toggle(k, "app", v)} label={`${kindLabel(k)}: ${t("Trong ứng dụng")}`} /></span>
                <span className="flex items-center text-[12.5px]"><span>{t("Đẩy")}</span><Switch on={cur(cp.data.data, k, "push")} disabled={busy === `${k}:push`} onChange={(v) => toggle(k, "push", v)} label={`${kindLabel(k)}: ${t("Đẩy")}`} /></span>
              </div>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 pt-3 border-t border-line flex items-center gap-3">
        <div className="min-w-0 flex-1"><div className="font-semibold text-[13.5px]">{t("Thông báo nổi khi đang mở ứng dụng")}</div><div className="text-[12.5px] text-muted">{t("Chỉ áp dụng trên thiết bị này.")}</div></div>
        <Switch on={prefs.toasts !== false} onChange={(v) => set({ toasts: v })} label={t("Thông báo nổi khi đang mở ứng dụng")} />
      </div>
    </Panel>
  );
}

function Devices() {
  const dq = usePushDevices();
  const remove = useRemovePushDevice();
  const [me, setMe] = useState(null);
  const [del, setDel] = useState(null);
  const [msg, setMsg] = useState({ tone: "", text: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => { currentEndpointHash().then(setMe); }, []);
  const isMine = (d) => !!me && (d.id === me || d.endpoint_hash === me);
  const run = async (fn, ok) => { setBusy(true); setMsg({ tone: "", text: "" }); try { await fn(); setMsg({ tone: "up", text: ok }); } catch (e) { setMsg({ tone: "down", text: e.message || t("Không thực hiện được.") }); } finally { setBusy(false); } };
  return (
    <Panel title={t("Thiết bị nhận thông báo đẩy")} icon={MonitorSmartphone}
      right={<button type="button" className="btn sm" disabled={busy || !(dq.data || []).length} onClick={() => run(testWebPush, t("Đã gửi thông báo thử tới các thiết bị."))}><SendHorizontal size={15} aria-hidden="true" /> {t("Gửi thử")}</button>}>
      {msg.text && <Notice tone={msg.tone || "info"} className="mb-3">{msg.text}</Notice>}
      <Async q={dq} rows={2} empty={t("Chưa có thiết bị nào bật thông báo đẩy.")} hint={t("Bật thông báo đẩy ở thẻ phía trên để thiết bị này nhận cảnh báo khi đã đóng ứng dụng.")}>
        {(list) => (
          <ul className="list-none m-0 p-0 grid">
            {list.map((d) => (
              <li key={d.id} className="py-2.5 border-b border-line last:border-0 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5"><b className="text-[13.5px]">{deviceName(d.user_agent)}</b>{isMine(d) && <Chip tone="up">{t("Thiết bị này")}</Chip>}</div>
                  <div className="text-[12px] text-faint">{t("Thêm {a}", { a: rel(d.created_at) })} · {d.last_ok_at ? t("gửi thành công gần nhất {a}", { a: rel(d.last_ok_at) }) : t("chưa gửi lần nào")}</div>
                </div>
                <button type="button" className="btn sm danger" onClick={() => setDel(d)} aria-label={t("Gỡ thiết bị {name}", { name: deviceName(d.user_agent) })}><Trash2 size={15} aria-hidden="true" /> {t("Gỡ")}</button>
              </li>
            ))}
          </ul>
        )}
      </Async>
      {del && (
        <Sheet title={t("Gỡ thiết bị này?")} onClose={() => setDel(null)}>
          <p className="m-0 mb-3 text-[14px]">{t("Thiết bị {name} sẽ không nhận thông báo đẩy nữa. Bạn có thể bật lại bất cứ lúc nào từ thiết bị đó.", { name: deviceName(del.user_agent) })}</p>
          <div className="flex gap-2"><button type="button" className="btn danger" disabled={busy} onClick={async () => { const d = del; setDel(null); await run(() => remove(d.id), t("Đã gỡ thiết bị.")); }}>{t("Gỡ thiết bị")}</button><button type="button" className="btn" onClick={() => setDel(null)}>{t("Giữ lại")}</button></div>
        </Sheet>
      )}
    </Panel>
  );
}

function Settings() {
  return (
    <>
      <PermissionCard />
      <WebPushCard />
      <RuleNotifyCard />
      <KindSettings />
      <Devices />
    </>
  );
}

function HistoryTab() {
  const ev = useRuleEvents(null, 50);
  return (
    <Panel title={t("Lịch sử kích hoạt cảnh báo")} icon={History} right={<a className="btn sm" href="#/canh-bao">{t("Quản lý cảnh báo")}</a>}>
      <Async q={ev} rows={3} isEmpty={(d) => !(d?.items || []).length} empty={t("Chưa có cảnh báo nào được kích hoạt.")}>
        {(d) => <RuleEventsList items={d.items} />}
      </Async>
    </Panel>
  );
}

export default function Notifications({ query }) {
  const [tab, setTab] = useState(["settings", "history"].includes(query?.tab) ? query.tab : "inbox");
  const [unread, setUnread] = useState(0);
  useClock();
  return (
    <>
      <PageHead title={t("Thông báo")} sub={t("Mọi sự kiện của bạn ở một nơi: cảnh báo đã đặt, giới hạn, báo cáo, bản tin và hỗ trợ. Hệ thống chỉ nhắc, không đặt hay đóng lệnh.")} />
      <Seg value={tab} onChange={setTab} label={t("Mục thông báo")} scroll
        options={[{ value: "inbox", label: unread ? t("Hộp thư ({n})", { n: unread }) : t("Hộp thư") }, { value: "settings", label: t("Cài đặt") }, { value: "history", label: t("Lịch sử cảnh báo") }]} />
      <div className={tab === "inbox" ? "grid gap-3" : "hidden"}><Inbox onUnread={setUnread} /></div>
      {tab === "settings" && <Settings />}
      {tab === "history" && <HistoryTab />}
    </>
  );
}
