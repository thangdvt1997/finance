import { useMemo, useState } from "react";
import { AlertTriangle, Clock3, History, Pencil, Plus, ShieldCheck, Trash2, Undo2 } from "lucide-react";
import { Async, Chip, Field, Notice, PageHead, Panel, Sheet, Skeleton } from "../components/ui";
import LimitMeter, { limitValue } from "../components/limits/LimitMeter";
import { accountTitle, useAuth } from "../lib/auth";
import { LIMIT_KEYS, isLoosening, limitMeta, useLimitHistory, useLimits, useSaveLimit } from "../lib/q_notif";
import { countdown, dateTime, rel } from "../lib/format";
import { useClock } from "../lib/clock";
import { t } from "../lib/i18n";

const LOOSEN_H = 24;

/** Đọc số người dùng nhập (chấp nhận dấu phẩy thập phân). */
function parseNum(s) {
  const x = String(s).trim().replace(",", ".");
  if (x === "" || !/^\d+(\.\d+)?$/.test(x)) return NaN;
  return Number(x);
}

function EditSheet({ k, item, unit, onClose, onSave }) {
  const meta = limitMeta(k);
  const cur = item?.value ?? null;
  const [val, setVal] = useState(cur != null ? String(cur) : meta.example);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const n = parseNum(val);
  const range = Number.isNaN(n) ? t("Nhập số hợp lệ.") : n < meta.min || n > meta.max ? t("Nhập số từ {lo} đến {hi}.", { lo: meta.min, hi: meta.max }) : meta.int && !Number.isInteger(n) ? t("Nhập số nguyên.") : "";
  const loosen = !range && isLoosening(k, cur, n);
  const same = !range && cur != null && n === cur;
  const cancels = same && item?.pending_effective_at != null;
  const unitText = k === "max_orders_day" ? t("lệnh") : "%";
  const submit = async (e) => {
    e.preventDefault();
    if (range || busy) return;
    setBusy(true); setErr("");
    try { await onSave(n); onClose(); } catch (x) { setErr(x.message); setBusy(false); }
  };
  const effAt = dateTime(Date.now() + LOOSEN_H * 3600e3);
  return (
    <Sheet title={cur == null ? t("Đặt: {name}", { name: meta.label }) : t("Sửa: {name}", { name: meta.label })} onClose={onClose}>
      <form className="grid gap-3.5" onSubmit={submit} noValidate>
        <p className="m-0 text-[13px] text-muted">{meta.hint}</p>
        <Field label={`${meta.label} (${unitText})`} error={val !== "" && range ? range : null}
          hint={cur != null ? t("Hiện hành: {v}", { v: limitValue(k, cur, unit) }) : t("Chưa đặt. Gợi ý: {v}", { v: meta.example })}>
          <input className="field num" inputMode="decimal" value={val} onChange={(e) => setVal(e.target.value)} autoComplete="off" />
        </Field>
        {loosen && (
          <Notice tone="warn" title={t("Đây là nới lỏng giới hạn")}>
            {t("Nới lỏng sẽ có hiệu lực sau 24 giờ (khoảng {at}). Giới hạn hiện hành vẫn giữ nguyên trong thời gian chờ. Siết chặt thì có hiệu lực ngay. Cách này giúp bạn không nới giới hạn bốc đồng ngay khi đang lỗ.", { at: effAt })}
          </Notice>
        )}
        {!range && !loosen && !same && cur != null && (
          <Notice tone="up" title={t("Đây là siết chặt")}>{t("Có hiệu lực ngay sau khi lưu.")}</Notice>
        )}
        {cancels && <Notice tone="info">{t("Đặt lại đúng giá trị hiện hành sẽ huỷ thay đổi đang chờ hiệu lực.")}</Notice>}
        {same && !cancels && <Notice tone="info">{t("Giá trị này đang áp dụng, không có gì thay đổi.")}</Notice>}
        {cur == null && !range && <Notice tone="info">{t("Giới hạn mới có hiệu lực ngay. Sau này muốn nới lỏng sẽ phải chờ 24 giờ.")}</Notice>}
        {err && <div role="alert" className="text-[13px] text-down">{err}</div>}
        <p className="m-0 text-[12.5px] text-faint">{t("Chỉ nhắc, không chặn lệnh: hệ thống không đặt, sửa hay đóng lệnh thay bạn.")}</p>
        <button className="btn primary" type="submit" disabled={!!range || busy || (same && !cancels)}>
          {busy ? t("Đang lưu...") : cancels ? t("Huỷ thay đổi đang chờ") : loosen ? t("Tôi hiểu, lên lịch nới lỏng sau 24 giờ") : t("Lưu giới hạn")}
        </button>
      </form>
    </Sheet>
  );
}

function resultText(r) {
  switch (r?.applied) {
    case "now": return t("Đã áp dụng ngay.");
    case "pending": return t("Đã lên lịch: có hiệu lực lúc {at}.", { at: dateTime(r.effective_at) });
    case "cancelled": return t("Đã huỷ thay đổi đang chờ hiệu lực.");
    default: return t("Không có gì thay đổi.");
  }
}

function LimitCard({ k, item, progress, onEdit, onDelete, onCancel, busy }) {
  const meta = limitMeta(k);
  const now = useClock();
  const set = item?.value != null;
  const pendAt = item?.pending_effective_at;
  const left = pendAt ? countdown(pendAt, now) : null;
  const removing = pendAt && item?.pending_value == null;
  return (
    <section className="panel" aria-label={meta.label}>
      <div className="panel-b grid gap-3">
        <LimitMeter k={k} item={item} progress={progress} showPending={false} />
        {!set && <p className="m-0 text-[13px] text-muted">{meta.hint}</p>}
        {pendAt && (
          <div className="rounded-xl border px-3 py-2.5 text-[13px] grid gap-2" style={{ borderColor: "color-mix(in srgb, var(--accent) 45%, transparent)", background: "var(--accent-bg)" }} role="group" aria-label={t("Thay đổi đang chờ hiệu lực")}>
            <div className="flex items-start gap-2"><Clock3 size={16} className="shrink-0 mt-[2px]" style={{ color: "var(--accent)" }} aria-hidden="true" />
              <div className="min-w-0">
                <div className="font-semibold">{removing ? t("Chờ hiệu lực: bỏ giới hạn") : t("Chờ hiệu lực: đổi sang {v}", { v: limitValue(k, item.pending_value, progress?.unit) })}</div>
                <div className="text-muted">{left ? t("Còn {d} (lúc {at}). Trong thời gian chờ, giới hạn hiện hành vẫn áp dụng.", { d: left, at: dateTime(pendAt) }) : t("Sắp có hiệu lực, đang cập nhật...")}</div>
              </div>
            </div>
            <div><button type="button" className="btn sm" disabled={busy} onClick={() => onCancel(k, item.value)}><Undo2 size={15} aria-hidden="true" /> {t("Huỷ thay đổi")}</button></div>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn sm" disabled={busy} onClick={() => onEdit(k)} aria-label={set ? t("Sửa: {name}", { name: meta.label }) : t("Đặt: {name}", { name: meta.label })}>
            {set ? <Pencil size={15} aria-hidden="true" /> : <Plus size={15} aria-hidden="true" />} {set ? t("Sửa") : t("Đặt giới hạn")}
          </button>
          {set && <button type="button" className="btn sm danger ml-auto" disabled={busy} onClick={() => onDelete(k)} aria-label={t("Xoá: {name}", { name: meta.label })}><Trash2 size={15} aria-hidden="true" /> {t("Xoá")}</button>}
        </div>
        {set && <p className="m-0 text-[12px] text-faint">{meta.hint}{item.updated_at ? ` · ${t("Cập nhật {a}", { a: rel(item.updated_at) })}` : ""}</p>}
      </div>
    </section>
  );
}

const APPLIED = (h) => (h.applied === "now" ? t("Có hiệu lực ngay") : h.applied === "pending" ? t("Chờ đến {at}", { at: dateTime(h.effective_at) }) : h.applied === "cancelled" ? t("Đã huỷ thay đổi chờ") : t("Không đổi"));

function HistoryPanel({ accountId }) {
  const hq = useLimitHistory(accountId, 30);
  return (
    <Panel title={t("Lịch sử thay đổi")} icon={History}>
      <Async q={hq} rows={3} empty={t("Chưa có thay đổi nào.")}>
        {(list) => (
          <ul className="list-none m-0 p-0 grid">
            {list.map((h, i) => {
              const m = limitMeta(h.key);
              return (
                <li key={`${h.ts}-${i}`} className="py-2.5 border-b border-line last:border-0 grid gap-0.5">
                  <div className="flex items-center gap-2 flex-wrap"><b className="text-[13.5px]">{m.label}</b><Chip tone={h.applied === "pending" ? "accent" : h.applied === "now" ? "up" : ""}>{APPLIED(h)}</Chip><span className="text-[12px] text-faint ml-auto num" title={dateTime(h.ts)}>{rel(h.ts)}</span></div>
                  <div className="text-[13px] num">{h.old == null ? t("chưa đặt") : limitValue(h.key, h.old)} → {h.new == null ? t("bỏ giới hạn") : limitValue(h.key, h.new)}</div>
                </li>
              );
            })}
          </ul>
        )}
      </Async>
    </Panel>
  );
}

export default function Limits() {
  const { active } = useAuth();
  const id = active?.id;
  const q = useLimits(id);
  const save = useSaveLimit(id);
  const [edit, setEdit] = useState(null);   // key
  const [del, setDel] = useState(null);     // key
  const [msg, setMsg] = useState(null);     // {tone,text}
  const [busy, setBusy] = useState(false);
  const items = useMemo(() => Object.fromEntries((q.data?.items || []).map((x) => [x.key, x])), [q.data]);
  const progress = q.data?.progress || {};
  const alerts = LIMIT_KEYS.filter((k) => k !== "monthly_target_pct" && ["danger", "hit"].includes(progress[k]?.level));

  const doSave = async (k, v) => { const r = await save(k, v); setMsg({ tone: r.applied === "now" ? "up" : "info", text: `${limitMeta(k).label}: ${resultText(r)}` }); return r; };
  const act = async (fn) => { setBusy(true); setMsg(null); try { await fn(); } catch (e) { setMsg({ tone: "down", text: e.message }); } finally { setBusy(false); } };
  const unavailable = q.isError && q.error?.status === 404;

  return (
    <>
      <PageHead title={t("Giới hạn & mục tiêu của tôi")} sub={t("Tự đặt giới hạn rủi ro và mục tiêu lợi nhuận cho tài khoản đang chọn. Hệ thống theo dõi và nhắc bạn khi gần chạm mức.")}
        right={active ? <Chip title={t("Tài khoản đang chọn")}>{accountTitle(active)}</Chip> : null} />
      <Notice tone="info" icon={ShieldCheck} title={t("Chỉ nhắc, không chặn lệnh")}>
        {t("Giới hạn là lời nhắc kỷ luật do bạn tự đặt: khi gần chạm hoặc chạm, bạn nhận thông báo. Hệ thống không đặt, sửa hay đóng lệnh. Siết chặt có hiệu lực ngay; nới lỏng (kể cả xoá giới hạn) có hiệu lực sau 24 giờ để tránh quyết định bốc đồng.")}
      </Notice>
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
      {!id ? <Notice tone="warn">{t("Chưa có tài khoản nào được ghép. Hãy ghép tài khoản MT để đặt giới hạn.")}</Notice>
        : q.isPending ? <Skeleton rows={5} h={64} />
        : unavailable ? <Notice tone="info" title={t("Giới hạn & mục tiêu chưa khả dụng")}>{t("Máy chủ chưa hỗ trợ tính năng này. Hãy quay lại sau.")}</Notice>
        : q.isError ? (
          <Notice tone="down" title={t("Không tải được giới hạn")} action={<button className="btn sm" onClick={() => q.refetch()}>{t("Thử lại")}</button>}>{q.error?.message}</Notice>
        ) : (
          <>
            {alerts.length > 0 && (
              <Notice tone="down" icon={AlertTriangle} title={t("{n} giới hạn cần chú ý", { n: alerts.length })}>
                {alerts.map((k) => limitMeta(k).short).join(", ")}. {t("Hãy xem lại kế hoạch giao dịch hôm nay.")}
              </Notice>
            )}
            <div className="grid gap-3 md:grid-cols-2">
              {LIMIT_KEYS.map((k) => (
                <LimitCard key={k} k={k} item={items[k]} progress={progress[k]} busy={busy}
                  onEdit={setEdit} onDelete={setDel} onCancel={(key, v) => act(() => doSave(key, v))} />
              ))}
            </div>
            <HistoryPanel accountId={id} />
          </>
        )}
      {edit && <EditSheet k={edit} item={items[edit]} unit={progress[edit]?.unit} onClose={() => setEdit(null)} onSave={(v) => doSave(edit, v)} />}
      {del && (
        <Sheet title={t("Xoá giới hạn?")} onClose={() => setDel(null)}>
          <p className="m-0 mb-2 text-[14px]">{t("Bạn sắp xoá: {name}.", { name: limitMeta(del).label })}</p>
          {limitMeta(del).loose
            ? <Notice tone="warn" title={t("Xoá là nới lỏng")}>{t("Giới hạn hiện hành vẫn áp dụng thêm 24 giờ rồi mới bị gỡ. Bạn có thể huỷ trong thời gian chờ.")}</Notice>
            : <Notice tone="info">{t("Mục tiêu sẽ bị gỡ ngay.")}</Notice>}
          <div className="flex gap-2 mt-3">
            <button type="button" className="btn danger" disabled={busy} onClick={() => { const k = del; setDel(null); act(() => doSave(k, null)); }}>{t("Xoá giới hạn")}</button>
            <button type="button" className="btn" onClick={() => setDel(null)}>{t("Giữ lại")}</button>
          </div>
        </Sheet>
      )}
    </>
  );
}
