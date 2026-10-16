// Thao tác hàng loạt, 2 BƯỚC: (1) prepare -> tóm tắt/bỏ qua/cảnh báo -> (2) gõ đúng cụm "XAC NHAN <n>" -> execute. Bí mật khi xoay chỉ hiển thị MỘT lần.
// Không lưu bí mật vào storage/URL; token xác nhận sống 120 giây, một lần dùng.
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Download, KeyRound, Pause, Play, RefreshCcw, Tag, UsersRound } from "lucide-react";
import { Dialog } from "../dialog";
import { toast } from "../../ux/bus";
import { csvCell, csvSafe, downloadText, fpost } from "../../lib/fleetApi";
import { useGroups, useTags } from "../../lib/fleetQueries";
import { Banner, ErrLine, Field, PRIMARY, SecretPanel, useLeaveGuard } from "./bits";

export const BULK_ACTIONS = [
  { id: "suspend", label: "Đình chỉ", icon: Pause, tone: "down", warn: "Khách không đăng nhập được và EA bị từ chối cho đến khi kích hoạt lại; mọi phiên của khách bị thu hồi." },
  { id: "activate", label: "Kích hoạt", icon: Play, tone: "up", warn: "Tài khoản đang đình chỉ sẽ hoạt động lại (tài khoản chờ duyệt cũng được duyệt)." },
  { id: "tag_add", label: "Gắn tag", icon: Tag, tone: "accent", param: "tag" },
  { id: "tag_remove", label: "Gỡ tag", icon: Tag, tone: "accent", param: "tag" },
  { id: "group_add", label: "Thêm vào nhóm", icon: UsersRound, tone: "accent", param: "group" },
  { id: "group_remove", label: "Gỡ khỏi nhóm", icon: UsersRound, tone: "accent", param: "group" },
  { id: "rotate_ea_token", label: "Xoay token EA", icon: RefreshCcw, tone: "down", secret: true, warn: "Token cũ bị thu hồi NGAY: mọi EA của các tài khoản này mất kết nối cho đến khi nhập token mới vào Inputs. Chỉ làm khi đã sẵn sàng phân phối token mới cho khách." },
  { id: "rotate_hmac", label: "Xoay HMAC", icon: KeyRound, tone: "down", secret: true, warn: "HMAC cũ bị thu hồi NGAY: EA phải cập nhật HmacSecret mới mới gửi được dữ liệu." },
];
const TAG_RE = /^[a-z0-9][a-z0-9_.-]{0,23}$/;
const msLeft = (t) => Math.max(0, t - Date.now());

export default function BulkDialog({ open, onClose, accountIds, onDone }) {
  const qc = useQueryClient();
  const groups = useGroups().data?.items || [];
  const tags = useTags().data?.items || [];
  const [action, setAction] = useState(null);
  const [tag, setTag] = useState("");
  const [groupId, setGroupId] = useState("");
  const [prep, setPrep] = useState(null);       // {token, summary, exp}
  const [typed, setTyped] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [, tick] = useState(0);
  const [acked, setAcked] = useState(false);
  const A = BULK_ACTIONS.find((a) => a.id === action);
  const secrets = useMemo(() => (res?.results || []).filter((r) => r.ok && r.secret), [res]);
  useLeaveGuard(secrets.length > 0 && !acked);

  useEffect(() => { if (open) { setAction(null); setTag(""); setGroupId(""); setPrep(null); setTyped(""); setRes(null); setErr(null); setAcked(false); } }, [open]);
  useEffect(() => { if (!prep) return; const t = setInterval(() => tick((x) => x + 1), 1000); return () => clearInterval(t); }, [prep]);
  const left = prep ? msLeft(prep.exp) : 0;
  useEffect(() => { if (prep && !res && left === 0) { setPrep(null); setTyped(""); setErr({ message: "Mã xác nhận đã hết hạn (120 giây). Hãy chuẩn bị lại." }); } }, [left]); // eslint-disable-line react-hooks/exhaustive-deps

  const params = A?.param === "tag" ? { tag: tag.trim().toLowerCase() } : A?.param === "group" ? { group_id: groupId } : {};
  const paramOk = !A?.param || (A.param === "tag" ? TAG_RE.test(params.tag) : !!groupId);
  const phrase = prep?.summary?.phrase || `XAC NHAN ${prep?.summary?.count ?? ""}`;

  const prepare = async () => {
    setBusy(true); setErr(null);
    const body = { action, account_ids: accountIds, params };
    if (JSON.stringify(body).length > 3900) { setErr({ message: "Danh sách chọn quá dài cho một lần gửi (giới hạn ~4KB). Hãy chọn ít tài khoản hơn mỗi lần." }); setBusy(false); return; }
    try {
      const r = await fpost("/bulk/prepare", body);
      setPrep({ token: r.confirm_token, summary: r.summary || {}, exp: Date.now() + (r.expires_in || 120) * 1000 });
      setTyped("");
    } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  const execute = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await fpost("/bulk/execute", { confirm_token: prep.token, phrase: typed.trim() });
      setRes(r); setPrep(null);
      qc.invalidateQueries({ queryKey: ["fl"] });
      const all = r.results || [];
      const ok = all.filter((x) => x.ok).length;
      toast({ tone: ok === all.length ? "ok" : "warn", title: `${A.label}: ${ok}/${all.length} tài khoản thành công` });
      onDone?.(r);
    } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  const close = () => { if (secrets.length && !acked) { setErr({ message: "Bí mật chỉ hiển thị một lần — hãy sao chép/tải về rồi tick xác nhận trước khi đóng." }); return; } onClose(); };
  const csv = () => downloadText(`xoay-${action}-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "")}.csv`, ["account_id,secret", ...secrets.map((r) => `${csvCell(csvSafe(r.account_id))},${csvCell(typeof r.secret === "string" ? r.secret : JSON.stringify(r.secret))}`)].join("\n"));

  const step = res ? 3 : prep ? 2 : 1;
  const skipped = prep?.summary?.skipped || [];
  const mm = `${Math.floor(left / 60000)}:${String(Math.floor((left % 60000) / 1000)).padStart(2, "0")}`;

  return (
    <Dialog open={open} onClose={close} title={`Thao tác hàng loạt · ${accountIds.length} tài khoản`} description={step === 1 ? "Bước 1/2 · Chọn thao tác và kiểm tra tác động" : step === 2 ? "Bước 2/2 · Xác nhận" : "Kết quả"} className="sm:max-w-[680px]"
      footer={step === 1 ? <>
        <button className="btn" onClick={close}>Huỷ</button>
        <button className={`btn ${PRIMARY}`} disabled={!A || !paramOk || busy} onClick={prepare}>{busy ? "Đang chuẩn bị…" : "Chuẩn bị & xem tóm tắt"}</button>
      </> : step === 2 ? <>
        <button className="btn" onClick={() => { setPrep(null); setTyped(""); }} disabled={busy}>Quay lại</button>
        <button className={`btn !border-transparent ${A?.tone === "down" ? "!bg-down !text-white" : PRIMARY}`} disabled={busy || typed.trim() !== phrase || (prep?.summary?.count ?? 0) === 0} onClick={execute}>{busy ? "Đang thực hiện…" : `Thực hiện: ${A?.label}`}</button>
      </> : <button className={`btn ${PRIMARY}`} onClick={close}>Đóng</button>}>
      <div className="p-3 grid gap-3 text-[13px]">
        {step === 1 && (
          <>
            <div role="radiogroup" aria-label="Thao tác" className="grid gap-2 grid-cols-2 sm:grid-cols-4">
              {BULK_ACTIONS.map((a) => (
                <button key={a.id} type="button" role="radio" aria-checked={action === a.id} onClick={() => { setAction(a.id); setErr(null); }}
                  className="btn !h-auto !py-2 flex-col !items-start" style={action === a.id ? { borderColor: "var(--accent)", background: "var(--accent-bg)" } : undefined}>
                  <a.icon size={15} className={a.tone === "down" ? "text-down" : "text-accent"} aria-hidden="true" /><span>{a.label}</span>
                </button>
              ))}
            </div>
            {A?.param === "tag" && (
              <Field label="Tag" htmlFor="bk-tag" help="Chữ thường/số/_ . - , tối đa 24 ký tự, tối đa 12 tag mỗi tài khoản." error={tag && !TAG_RE.test(tag.trim().toLowerCase()) ? "Tag không hợp lệ." : null}>
                <input id="bk-tag" list="bk-taglist" className="field" value={tag} onChange={(e) => setTag(e.target.value)} maxLength={24} data-autofocus />
                <datalist id="bk-taglist">{tags.map((t) => <option key={t.tag} value={t.tag} />)}</datalist>
              </Field>
            )}
            {A?.param === "group" && (
              <Field label="Nhóm" htmlFor="bk-grp" help={!groups.length ? "Chưa có nhóm — tạo ở mục “Quản lý nhóm”." : undefined}>
                <select id="bk-grp" className="field" value={groupId} onChange={(e) => setGroupId(e.target.value)}><option value="">— chọn nhóm —</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name} ({g.members})</option>)}</select>
              </Field>
            )}
            {A?.warn && <Banner tone="warn" title="Tác động">{A.warn}</Banner>}
            <ErrLine error={err} />
          </>
        )}
        {step === 2 && prep && (
          <>
            <div className="flex flex-wrap items-center gap-2"><b>{A.label}</b><span className="fl-pill t-info num">{prep.summary.count ?? accountIds.length} tài khoản sẽ bị tác động</span>
              <span className="ml-auto text-[12px] text-muted num">Mã xác nhận hết hạn sau {mm}</span></div>
            {skipped.length > 0 && (
              <Banner tone="warn" title={`${skipped.length} tài khoản sẽ bị bỏ qua`}>
                <ul className="m-0 mt-1 pl-4 max-h-32 overflow-auto text-[12px]">{skipped.map((s) => <li key={s.account_id}><span className="num">{s.account_id}</span> — {s.reason}</li>)}</ul>
              </Banner>
            )}
            {A.warn && <Banner tone="bad" icon={AlertTriangle} title="Cảnh báo">{A.warn}</Banner>}
            <Field label={<>Gõ đúng cụm <b className="num">{phrase}</b> để xác nhận</>} htmlFor="bk-phrase">
              <input id="bk-phrase" className="field num" autoComplete="off" spellCheck={false} value={typed} onChange={(e) => setTyped(e.target.value)} data-autofocus aria-invalid={typed !== "" && typed.trim() !== phrase} />
            </Field>
            <p className="m-0 text-[12px] text-muted">Thao tác được ghi vào nhật ký kiểm toán cho từng tài khoản và một bản ghi gộp.</p>
            <ErrLine error={err} />
          </>
        )}
        {step === 3 && res && (
          <>
            <div className="max-h-56 overflow-auto rounded-md border border-line">
              <table className="fl-tbl"><thead><tr><th>Tài khoản</th><th>Kết quả</th></tr></thead>
                <tbody>{(res.results || []).map((r) => (
                  <tr key={r.account_id} style={{ cursor: "default" }}><td className="c-id">{r.account_id}</td>
                    <td>{r.ok ? <span className="fl-pill t-ok">Thành công</span> : <span className="fl-pill t-bad" title={r.error}>Lỗi{r.error ? `: ${r.error}` : ""}</span>}</td></tr>))}</tbody></table>
            </div>
            {secrets.length > 0 && (
              <>
                <SecretPanel title="Bí mật mới — chỉ hiển thị MỘT lần" items={secrets.map((r) => ({ k: r.account_id, v: typeof r.secret === "string" ? r.secret : JSON.stringify(r.secret) }))} filename={`xoay-${action}.txt`} onAck={setAcked} />
                <div><button type="button" className="btn" onClick={csv}><Download size={13} aria-hidden="true" />Tải CSV (account_id, secret)</button></div>
              </>
            )}
            <ErrLine error={err} />
          </>
        )}
      </div>
    </Dialog>
  );
}
