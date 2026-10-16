// Nhập CSV hàng loạt -> xem trước theo dòng (lỗi/cảnh báo/ok) -> commit -> "Thẻ onboarding" (in A4 / tải CSV). Secret chỉ ở state của hộp thoại này:
// KHÔNG lưu vào localStorage/sessionStorage/URL; rời trang là mất. Master phải bật TOTP (máy chủ trả 403 totp_required).
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, FileUp, Printer, Upload, XOctagon } from "lucide-react";
import { Dialog } from "../dialog";
import { toast } from "../../ux/bus";
import { csvCell, csvSafe, downloadText, fpost, openTotpWizard } from "../../lib/fleetApi";
import { getBridgeUrl } from "../../lib/clientsApi";
import { usePerm } from "../../lib/fleetQueries";
import { Banner, ErrLine, Field, Pill, PRIMARY, useLeaveGuard, fmtDTfull } from "./bits";

export const CSV_HEADER = "platform,login,server,label,group,tags,notes";
export const CSV_SAMPLE = `${CSV_HEADER}\nmt5,12345678,BrokerA-Live,Khach A - chien luoc 1,Khach VIP,vip;scalp,Hop dong 2026\nmt4,87654321,BrokerB-Demo,Khach B,,,`;
const MAX_BYTES = 200_000;

const steps3 = (origin, row, have) => [
  `Chép file EA vào thư mục Experts trong Data Folder của ${row.platform === "mt5" ? "MT5" : "MT4"} (File → Open Data Folder), Refresh Navigator; Tools → Options → Expert Advisors → tick “Allow WebRequest” và thêm ${origin}.`,
  `Kéo EA vào một chart; tab Inputs đặt BridgeUrl, AccountId = ${row.account_id}, Token${have.hmac_secret ? ", HmacSecret" : ""}. Bật AutoTrading chung. EA chỉ ĐỌC, không đặt lệnh; nên dùng mật khẩu investor.`,
  `Sau ~1 phút tài khoản chuyển “Trực tuyến”. Khách vào ${origin}/c/, đăng nhập ID MT + passcode (hoặc ghép cặp bằng mã) rồi đổi mật khẩu.`,
];

/** Một thẻ onboarding (dùng cho cả xem trước trên màn hình lẫn bản in). */
function Card({ c, print }) {
  const s = c.secrets || {};
  const url = getBridgeUrl();
  let origin = url; try { origin = new URL(url).origin; } catch { /* giữ nguyên */ }
  const st = steps3(origin, c, s);
  const rows = [
    ["Tài khoản", `${c.account_id}${c.server ? ` @ ${c.server}` : ""}`], ["Passcode", s.passcode], ["Mã ghép cặp", s.pairing_code ? `${s.pairing_code}${s.pairing_expires_at ? `  (hạn ${fmtDTfull(s.pairing_expires_at)})` : ""}` : null],
    ["EA token", s.ea_token], ["HMAC secret", s.hmac_secret], ["BridgeUrl", url],
  ].filter(([, v]) => v);
  return (
    <article className={print ? "fl-pcard" : "fl-obcard"} aria-label={`Thẻ onboarding ${c.account_id}`}>
      {print ? <h3><span>{c.label || c.account_id}</span><small>Thẻ onboarding · chỉ-đọc</small></h3> : <h3>{c.label || c.account_id}</h3>}
      <dl>{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      <ol>{st.map((t, i) => <li key={i}>{t}</li>)}</ol>
      {print && <div className="fl-pwarn">Giữ bí mật. Thẻ chỉ in một lần — máy chủ không lưu bản rõ. Mất thẻ: master cấp lại passcode/mã ghép cặp/token.</div>}
    </article>
  );
}

function PrintSheet({ cards, onDone }) {
  useEffect(() => {
    document.body.classList.add("fl-printing");
    const end = () => { document.body.classList.remove("fl-printing"); onDone(); };
    addEventListener("afterprint", end, { once: true });
    const t = setTimeout(() => window.print(), 120);
    return () => { clearTimeout(t); removeEventListener("afterprint", end); document.body.classList.remove("fl-printing"); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return createPortal(<section id="fl-print" aria-hidden="true"><div className="fl-pgrid">{cards.map((c) => <Card key={c.account_id} c={c} print />)}</div></section>, document.body);
}

export function cardsCsv(cards) {
  const head = "label,account_id,platform,server,passcode,pairing_code,pairing_expires_at,ea_token,hmac_secret";
  const L = cards.map((c) => { const s = c.secrets || {}; return [c.label, c.account_id, c.platform, c.server, s.passcode, s.pairing_code, s.pairing_expires_at, s.ea_token, s.hmac_secret].map((v) => csvCell(csvSafe(v))).join(","); });
  return [head, ...L].join("\n");
}

export default function ImportFlow({ open, onClose }) {
  const qc = useQueryClient();
  const perm = usePerm();
  const [csv, setCsv] = useState("");
  const [prev, setPrev] = useState(null);       // {token, rows, summary}
  const [out, setOut] = useState(null);         // {cards, failed}
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [acked, setAcked] = useState(false);
  const [printing, setPrinting] = useState(false);
  const file = useRef(null);
  const step = out ? 3 : prev ? 2 : 1;
  const hasSecrets = !!out?.cards?.length;
  useLeaveGuard(hasSecrets && !acked);

  useEffect(() => { if (open) { setCsv(""); setPrev(null); setOut(null); setErr(null); setAcked(false); setBusy(false); setPrinting(false); } }, [open]);

  const bytes = new Blob([csv]).size;
  const loadFile = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    if (f.size > MAX_BYTES) { setErr({ message: `Tệp quá lớn (${Math.round(f.size / 1000)}KB > 200KB, tối đa 500 dòng).` }); return; }
    setCsv(await f.text()); setErr(null);
  };
  const preview = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await fpost("/import/preview", { csv });
      setPrev({ token: r.preview_token, rows: r.rows || [], summary: r.summary || {} });
    } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  const commit = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await fpost("/import/commit", { preview_token: prev.token });
      const byLine = new Map(prev.rows.map((x) => [x.line, x]));
      const cards = (r.created || []).map((c) => { const p = byLine.get(c.line) || {}; return { ...c, label: p.label || c.account_id, platform: p.platform || c.account_id.split(":")[0], server: p.server || "", secrets: c.secrets || {} }; });
      setOut({ cards, failed: r.failed || [] });
      qc.invalidateQueries({ queryKey: ["fl"] });
      toast({ tone: cards.length ? "ok" : "warn", title: `Đã tạo ${cards.length} tài khoản`, body: r.failed?.length ? `${r.failed.length} dòng lỗi` : undefined });
    } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  const close = () => { if (hasSecrets && !acked) { setErr({ message: "Secret chỉ hiển thị một lần — tải CSV hoặc in thẻ rồi tick xác nhận trước khi đóng." }); return; } onClose(); };
  const okN = prev?.summary?.ok ?? prev?.rows.filter((r) => r.ok).length ?? 0;
  const warnN = useMemo(() => prev?.rows.filter((r) => r.ok && r.warnings?.length).length || 0, [prev]);

  return (
    <>
      <Dialog open={open} onClose={close} title="Nhập tài khoản hàng loạt (CSV)" className="sm:max-w-[980px]" description={step === 1 ? "Bước 1/3 · Nạp CSV" : step === 2 ? "Bước 2/3 · Xem trước theo dòng" : "Bước 3/3 · Thẻ onboarding"}
        footer={step === 1 ? <>
          <button className="btn" onClick={close}>Huỷ</button>
          <button className={`btn ${PRIMARY}`} disabled={!csv.trim() || bytes > MAX_BYTES || busy} onClick={preview}>{busy ? "Đang kiểm tra…" : "Xem trước"}</button>
        </> : step === 2 ? <>
          <button className="btn" onClick={() => { setPrev(null); setErr(null); }} disabled={busy}>Quay lại sửa CSV</button>
          <button className={`btn ${PRIMARY}`} disabled={busy || okN === 0} onClick={commit}>{busy ? "Đang tạo tài khoản…" : `Tạo ${okN} tài khoản hợp lệ`}</button>
        </> : <>
          <label className="mr-auto fl-check"><input type="checkbox" checked={acked} onChange={(e) => setAcked(e.target.checked)} /><span>Tôi đã lưu/in các thẻ này — rời đi là mất secret</span></label>
          <button className={`btn ${PRIMARY}`} onClick={close} disabled={hasSecrets && !acked}>Đóng</button>
        </>}>
        <div className="p-3 grid gap-3 text-[13px]">
          {perm.totpRequired && perm.isMaster && (
            <Banner tone="warn" title="Cần bật xác thực hai bước (TOTP) trước khi nhập" actions={<button type="button" className="btn" onClick={openTotpWizard}>Bật TOTP</button>}>
              Nhập CSV tạo tài khoản kèm bí mật nên chỉ master đã bật TOTP mới dùng được. Làm theo trình hướng dẫn rồi quay lại bước này — nội dung CSV bạn đã dán vẫn giữ nguyên.
            </Banner>
          )}
          {step === 1 && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" className="btn" onClick={() => downloadText("mau-nhap-tai-khoan.csv", CSV_SAMPLE)}><Download size={13} aria-hidden="true" />Tải mẫu CSV</button>
                <button type="button" className="btn" onClick={() => file.current?.click()}><FileUp size={13} aria-hidden="true" />Chọn tệp .csv</button>
                <input ref={file} type="file" accept=".csv,text/csv,text/plain" className="fl-sr" tabIndex={-1} aria-hidden="true" onChange={loadFile} />
                <span className="text-[12px] text-muted ml-auto num">{bytes.toLocaleString("vi-VN")} / 200.000 byte</span>
              </div>
              <Field label="Dán nội dung CSV" htmlFor="imp-csv" help={`Cột: ${CSV_HEADER} (tối đa 500 dòng). Nhóm phải tồn tại; tag cách nhau bằng dấu chấm phẩy. Số tài khoản trùng sẽ bị báo lỗi.`}>
                <textarea id="imp-csv" className="field fl-mono" rows={10} spellCheck={false} value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={CSV_SAMPLE} data-autofocus />
              </Field>
              <ErrLine error={err} />
            </>
          )}
          {step === 2 && prev && (
            <>
              <div className="flex flex-wrap gap-2 items-center">
                <Pill tone="info">{prev.summary.total ?? prev.rows.length} dòng</Pill>
                <Pill tone="ok" icon={CheckCircle2}>{okN} hợp lệ</Pill>
                {warnN > 0 && <Pill tone="warn" icon={AlertTriangle}>{warnN} có cảnh báo</Pill>}
                <Pill tone={prev.summary.error ? "bad" : "mute"} icon={XOctagon}>{prev.summary.error ?? 0} lỗi (sẽ bị bỏ qua)</Pill>
              </div>
              <div className="overflow-auto max-h-[46dvh] rounded-md border border-line">
                <table className="fl-tbl" style={{ minWidth: 760 }}>
                  <caption className="fl-sr">Xem trước từng dòng CSV</caption>
                  <thead><tr><th>Dòng</th><th>Trạng thái</th><th>Nền tảng</th><th>Số TK</th><th>Server</th><th>Nhãn</th><th>Nhóm</th><th>Tag</th></tr></thead>
                  <tbody>
                    {prev.rows.map((r) => (
                      <tr key={r.line} style={{ cursor: "default" }} className={!r.ok ? "fl-prevrow-bad" : r.warnings?.length ? "fl-prevrow-warn" : undefined}>
                        <td className="num">{r.line}</td>
                        <td>{!r.ok ? <Pill tone="bad" icon={XOctagon}>Lỗi</Pill> : r.warnings?.length ? <Pill tone="warn" icon={AlertTriangle}>Cảnh báo</Pill> : <Pill tone="ok" icon={CheckCircle2}>OK</Pill>}
                          {[...(r.errors || []), ...(r.warnings || [])].map((m, i) => <span key={i} className="c-sub" style={{ whiteSpace: "normal", maxWidth: 260 }}>{m}</span>)}</td>
                        <td>{r.platform}</td><td className="num">{r.login}</td><td>{r.server}</td><td>{r.label}</td><td>{r.group}</td><td>{Array.isArray(r.tags) ? r.tags.join(", ") : r.tags}</td>
                      </tr>))}
                  </tbody>
                </table>
              </div>
              <ErrLine error={err} />
            </>
          )}
          {step === 3 && out && (
            <>
              <Banner tone="bad" icon={AlertTriangle} role="alert" title="Secret chỉ hiển thị MỘT lần — rời trang là mất">
                Máy chủ không lưu bản rõ của passcode, mã ghép cặp, EA token và HMAC secret. Hãy <b>tải CSV</b> hoặc <b>in / lưu PDF</b> NGAY rồi cất ở nơi an toàn. Tệp tải về chứa bí mật — xoá sau khi phân phối.
              </Banner>
              {out.failed.length > 0 && <Banner tone="warn" title={`${out.failed.length} dòng không tạo được`}><ul className="m-0 pl-4 text-[12px]">{out.failed.map((f) => <li key={f.line}>Dòng {f.line}: {f.error}</li>)}</ul></Banner>}
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn" disabled={!hasSecrets} onClick={() => downloadText(`the-onboarding-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "")}.csv`, cardsCsv(out.cards))}><Download size={13} aria-hidden="true" />Tải CSV</button>
                <button type="button" className="btn" disabled={!hasSecrets} onClick={() => setPrinting(true)}><Printer size={13} aria-hidden="true" />In / Lưu PDF (A4, 2 thẻ/trang)</button>
              </div>
              {hasSecrets ? <div className="fl-cards">{out.cards.map((c) => <Card key={c.account_id} c={c} />)}</div> : <p className="m-0 text-muted">Không có tài khoản nào được tạo.</p>}
              <ErrLine error={err} />
            </>
          )}
        </div>
      </Dialog>
      {printing && out && <PrintSheet cards={out.cards} onDone={() => setPrinting(false)} />}
    </>
  );
}
