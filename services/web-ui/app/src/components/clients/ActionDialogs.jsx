import { useEffect, useState } from "react";
import { AlertTriangle, Eye, KeyRound, LockOpen, LogOut, Pause, Play, Printer, QrCode, RefreshCcw, ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { Dialog } from "../dialog";
import { Chip, cn } from "../ui";
import { useAdminRun } from "../../lib/clientsQueries";
import { getBridgeUrl, setBridgeUrl } from "../../lib/clientsApi";
import { CopyBtn, fmtDT } from "./bits";

/** Thông số từng hành động. secret: kết quả chứa bí mật hiển thị 1 lần. Mọi hành động đều được auth ghi vào nhật ký kiểm toán. */
export const ACTIONS = {
  passcode: { label: "Cấp lại passcode", icon: KeyRound, tone: "accent", secret: true, impact: ["Passcode cũ mất hiệu lực ngay; khách bị đăng xuất khỏi mọi phiên và phải đổi mật khẩu ở lần đăng nhập đầu.", "Gỡ khoá tạm do nhập sai (nếu có).", "Passcode mới chỉ hiển thị MỘT lần."] },
  pairing: { label: "Cấp mã ghép cặp", icon: QrCode, tone: "accent", secret: true, impact: ["Mã ghép cặp cũ mất hiệu lực; mã mới có hạn dùng (mặc định 7 ngày).", "Khách dùng mã này để ghép cặp lần đầu và tự đặt mật khẩu."] },
  rotate: { label: "Xoay token EA", icon: RefreshCcw, tone: "accent", secret: true, impact: ["Token (và HMAC nếu có) cũ bị thu hồi ngay: EA đang chạy sẽ báo 401 và mất kết nối cho đến khi nhập token mới vào Inputs.", "Nên làm lúc không cần theo dõi liên tục tài khoản này."] },
  suspend: { label: "Đình chỉ", icon: Pause, tone: "down", impact: ["Khách không đăng nhập được; mọi phiên đang mở bị thu hồi.", "Có thể kích hoạt lại bất cứ lúc nào."] },
  activate: { label: "Kích hoạt lại", icon: Play, tone: "up", impact: ["Khách đăng nhập lại được và EA gửi dữ liệu bình thường."] },
  logout: { label: "Ép đăng xuất", icon: LogOut, tone: "accent", impact: ["Mọi phiên đăng nhập đang mở của khách bị thu hồi ngay.", "Khách vẫn đăng nhập lại được bằng mật khẩu."] },
  unlock: { label: "Mở khoá", icon: LockOpen, tone: "accent", impact: ["Gỡ khoá tạm và đặt lại bộ đếm đăng nhập sai của khách."] },
  delete: { label: "Xoá tài khoản", icon: Trash2, tone: "down", impact: ["Xoá tài khoản MT khỏi hệ thống cùng hồ sơ đăng nhập của khách (nếu không còn tài khoản nào khác); token/HMAC EA bị huỷ.", "KHÔNG hoàn tác được trên giao diện. Dữ liệu snapshot/nhật ký giao dịch đã lưu vẫn còn ở kho dữ liệu."] },
  impersonate: { label: "Xem như khách hàng", icon: Eye, tone: "accent", impact: ["Mở chế độ CHỈ-ĐỌC hiển thị đúng dữ liệu khách nhìn thấy; không thể thay đổi gì.", "Việc bắt đầu xem được ghi vào nhật ký kiểm toán (view_as)."] },
};

const PRIMARY = "btn !bg-accent !text-[color:var(--accent-fg)] !border-transparent";

function useClose(secret, acked, onClose) {
  const [nag, setNag] = useState(false);
  return { nag, close: () => { if (secret && !acked) { setNag(true); return; } onClose(); } };
}

/** Hộp thoại xác nhận 2 bước: (1) xem tác động, (2) gõ số tài khoản để xác nhận. Ghi audit ở máy chủ auth. */
export function ConfirmDialog({ kind, row, onClose, onDone }) {
  const A = ACTIONS[kind];
  const { run } = useAdminRun();
  const [step, setStep] = useState(1);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [secret, setSecret] = useState(null);
  const [acked, setAcked] = useState(false);
  const { nag, close } = useClose(secret, acked, onClose);
  useEffect(() => { setStep(1); setTyped(""); setErr(""); setSecret(null); setAcked(false); }, [kind, row?.account_id]);
  if (!A || !row) return null;
  const Icon = A.icon;
  const need = String(row.login);

  const go = async () => {
    setBusy(true); setErr("");
    try {
      const res = await run(row, kind);
      if (A.secret) setSecret(res);
      else { onDone?.(kind, res); onClose(); }
    } catch (e) { setErr(e.message || "Không thực hiện được."); }
    setBusy(false);
  };

  if (secret) {
    return (
      <Dialog open onClose={close} title={`${A.label} · ${row.account_id}`} footer={
        <>
          <label className="mr-auto flex items-center gap-2 text-[12.5px]"><input type="checkbox" checked={acked} onChange={(e) => setAcked(e.target.checked)} /> Tôi đã lưu/in thông tin này</label>
          <button className="btn" onClick={() => window.print()}><Printer size={14} aria-hidden="true" /> In thẻ</button>
          <button className={PRIMARY} disabled={!acked} onClick={onClose}>Đóng</button>
        </>}>
        {nag && <p role="alert" className="m-3 mb-0 text-down text-[12.5px]">Bí mật chỉ hiển thị một lần. Hãy sao chép/in rồi tick xác nhận trước khi đóng.</p>}
        <OnboardingCard row={row} data={secret} kind={kind} />
      </Dialog>
    );
  }

  return (
    <Dialog open onClose={onClose} title={`${A.label} · ${row.account_id}`} description={step === 1 ? "Bước 1/2 · Kiểm tra tác động" : "Bước 2/2 · Xác nhận"} footer={
      <>
        {err && <span role="alert" className="mr-auto text-down text-[12.5px]">{err}</span>}
        {step === 2 && <button className="btn" onClick={() => setStep(1)} disabled={busy}>Quay lại</button>}
        <button className="btn" onClick={onClose} disabled={busy}>Huỷ</button>
        {step === 1
          ? <button className={PRIMARY} onClick={() => setStep(2)} data-autofocus>Tiếp tục</button>
          : <button className={cn("btn !border-transparent", A.tone === "down" ? "!bg-down !text-white" : "!bg-accent !text-[color:var(--accent-fg)]")} disabled={busy || typed.trim() !== need} onClick={go}>{busy ? "Đang thực hiện…" : A.label}</button>}
      </>}>
      <div className="p-3 grid gap-3 text-[13px]">
        <div className="flex flex-wrap items-center gap-2"><Icon size={16} className={A.tone === "down" ? "text-down" : "text-accent"} aria-hidden="true" /><b>{A.label}</b><Chip>{row.client_name || "Chưa gán khách"}</Chip><Chip className="num">{row.account_id}</Chip></div>
        {step === 1 ? (
          <ul className="m-0 pl-5 grid gap-1">{A.impact.map((t) => <li key={t}>{t}</li>)}</ul>
        ) : (
          <>
            <p className="m-0 flex gap-2 items-start rounded-md border border-line2 bg-panel2 p-2"><AlertTriangle size={15} className="text-accent shrink-0 mt-[2px]" aria-hidden="true" />Thao tác được ghi vào nhật ký kiểm toán (chuỗi băm) kèm tài khoản master, IP và thời gian.</p>
            <label className="grid gap-1"><span>Gõ số tài khoản <b className="num">{need}</b> để xác nhận</span>
              <input className="field num" inputMode="numeric" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} data-autofocus aria-invalid={typed !== "" && typed.trim() !== need} /></label>
          </>
        )}
      </div>
    </Dialog>
  );
}

const field = "grid gap-1";
export function CreateDialog({ onClose, onCreated }) {
  const { create } = useAdminRun();
  const [f, setF] = useState({ platform: "mt5", login: "", server: "", label: "", notes: "", bridge: getBridgeUrl() });
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null); const [acked, setAcked] = useState(false);
  const { nag, close } = useClose(res, acked, onClose);
  const ok = /^\d{4,12}$/.test(f.login) && /^[\w .:\-/()]{0,64}$/.test(f.server) && f.server.trim().length >= 2 && /^https?:\/\/\S+$/.test(f.bridge);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault(); if (!ok || busy) return; setBusy(true); setErr("");
    try { setBridgeUrl(f.bridge.trim()); const r = await create({ ...f, login: f.login.trim(), server: f.server.trim(), label: f.label.trim(), notes: f.notes.trim() }); setRes(r); onCreated?.(r); }
    catch (x) { setErr(x.message || "Không tạo được tài khoản."); }
    setBusy(false);
  };
  if (res) {
    return (
      <Dialog open onClose={close} title="Tài khoản đã tạo · thẻ onboarding" footer={
        <>
          <label className="mr-auto flex items-center gap-2 text-[12.5px]"><input type="checkbox" checked={acked} onChange={(e) => setAcked(e.target.checked)} /> Tôi đã lưu/in thông tin này</label>
          <button className="btn" onClick={() => window.print()}><Printer size={14} aria-hidden="true" /> In thẻ</button>
          <button className={PRIMARY} disabled={!acked} onClick={onClose}>Xong</button>
        </>}>
        {nag && <p role="alert" className="m-3 mb-0 text-down text-[12.5px]">Bí mật chỉ hiển thị một lần. Hãy sao chép/in rồi tick xác nhận trước khi đóng.</p>}
        <OnboardingCard row={res.account} data={res} kind="create" />
      </Dialog>
    );
  }
  return (
    <Dialog open onClose={onClose} title="Tạo tài khoản MT mới" description="Hệ thống sinh passcode, mã ghép cặp và token EA. Chỉ cần số tài khoản — KHÔNG nhập mật khẩu giao dịch/investor." footer={
      <>
        {err && <span role="alert" className="mr-auto text-down text-[12.5px]">{err}</span>}
        <button type="button" className="btn" onClick={onClose}>Huỷ</button>
        <button type="submit" form="create-acc" className={PRIMARY} disabled={!ok || busy}><UserPlus size={14} aria-hidden="true" />{busy ? "Đang tạo…" : "Tạo tài khoản"}</button>
      </>}>
      <form id="create-acc" onSubmit={submit} className="p-3 grid gap-3 text-[13px]">
        <div className={field}><span className="text-muted text-[12px]" id="pf">Nền tảng</span>
          <div className="seg" role="group" aria-labelledby="pf">{["mt5", "mt4"].map((p) => <button type="button" key={p} aria-pressed={f.platform === p} onClick={() => setF({ ...f, platform: p })}>{p.toUpperCase()}</button>)}</div></div>
        <label className={field}><span className="text-muted text-[12px]">Số tài khoản (login)</span><input className="field num" inputMode="numeric" autoComplete="off" value={f.login} onChange={set("login")} placeholder="vd. 12345678" aria-invalid={f.login !== "" && !/^\d{4,12}$/.test(f.login)} data-autofocus /></label>
        <label className={field}><span className="text-muted text-[12px]">Server broker</span><input className="field" autoComplete="off" value={f.server} onChange={set("server")} placeholder="vd. Exness-MT5Real8" maxLength={64} /></label>
        <label className={field}><span className="text-muted text-[12px]">Nhãn / tên hiển thị của khách</span><input className="field" value={f.label} onChange={set("label")} maxLength={80} placeholder="vd. Nguyễn Văn An · Scalp vàng" /></label>
        <label className={field}><span className="text-muted text-[12px]">Ghi chú nội bộ (tuỳ chọn)</span><textarea className="field !h-auto py-1.5" rows={2} maxLength={500} value={f.notes} onChange={set("notes")} /></label>
        <label className={field}><span className="text-muted text-[12px]">BridgeUrl mà EA gọi tới (dùng trong hướng dẫn cài; nhớ trên trình duyệt này)</span><input className="field num" value={f.bridge} onChange={set("bridge")} inputMode="url" /></label>
      </form>
    </Dialog>
  );
}

function Secret({ k, v }) {
  return (
    <div className="onb-row">
      <span className="onb-k">{k}</span>
      <code className="onb-v num">{v}</code>
      <CopyBtn text={v} small className="no-print" />
    </div>
  );
}

/** Thẻ onboarding (in được). Bí mật chỉ nằm trong state của hộp thoại này, không vào cache truy vấn. */
export function OnboardingCard({ row, data, kind }) {
  const url = data.ingest_url || getBridgeUrl();
  const mt5 = row.platform === "mt5";
  const have = { pass: data.passcode, pair: data.pairing_code, tok: data.ea_token, hmac: data.ea_hmac_secret };
  const title = { create: "Thẻ onboarding", passcode: "Passcode mới", pairing: "Mã ghép cặp mới", rotate: "Token EA mới" }[kind] || "Thông tin cấp phát";
  const all = [`Tài khoản: ${row.account_id}${row.server ? ` @ ${row.server}` : ""}`, have.pass && `Passcode: ${have.pass}`, have.pair && `Mã ghép cặp: ${have.pair}`, have.tok && `EA token: ${have.tok}`, have.hmac && `HMAC secret: ${have.hmac}`, (have.tok || kind === "create") && `BridgeUrl: ${url}`].filter(Boolean).join("\n");
  let origin = url; try { origin = new URL(url).origin; } catch { /* giữ nguyên */ }
  return (
    <div id="onb-print" className="onb p-3 grid gap-3 text-[13px]">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldCheck size={16} className="text-up" aria-hidden="true" /><b className="text-[14px]">{title}</b>
        <Chip className="num">{row.account_id}</Chip>{row.label && <Chip>{row.label}</Chip>}
        <CopyBtn text={all} label="Chép tất cả" small className="ml-auto no-print" />
      </div>
      <p role="alert" className="m-0 flex gap-2 items-start rounded-md border border-accent/50 bg-[var(--accent-bg)] px-3 py-2 text-[12.5px]"><AlertTriangle size={15} className="text-accent shrink-0 mt-[2px]" aria-hidden="true" /><span><b>Chỉ hiển thị MỘT lần.</b> Sau khi đóng hộp thoại sẽ không xem lại được; chỉ có thể cấp lại. Gửi cho khách qua kênh an toàn.</span></p>
      {data.warn && <p role="alert" className="m-0 text-down text-[12.5px]">{data.warn}</p>}
      <div className="grid gap-2">
        {have.pass && <Secret k="Passcode đăng nhập (đổi ở lần đăng nhập đầu)" v={have.pass} />}
        {have.pair && <Secret k={`Mã ghép cặp${data.pairing_expires_at ? ` (hết hạn ${fmtDT(data.pairing_expires_at)})` : ""}`} v={have.pair} />}
        {have.tok && <Secret k="EA token (input Token)" v={have.tok} />}
        {have.hmac && <Secret k="HMAC secret (input HmacSecret)" v={have.hmac} />}
        {(have.tok || kind === "create") && <Secret k="BridgeUrl" v={url} />}
      </div>
      {(have.tok || kind === "create") && (
        <section aria-label="Hướng dẫn cài EA">
          <h3 className="m-0 mb-1 text-[12.5px] font-semibold">Cài EA đọc-chỉ (MTAgentReadOnly) trên {mt5 ? "MT5" : "MT4"}</h3>
          <ol className="m-0 pl-5 grid gap-1 text-[12.5px] text-muted">
            <li>Chép file EA vào thư mục <code>{mt5 ? "MQL5/Experts" : "MQL4/Experts"}</code> (File → Open Data Folder), rồi Refresh trong Navigator.</li>
            <li>Tools → Options → Expert Advisors → tick “Allow WebRequest for listed URL” và thêm <code>{origin}</code>.</li>
            <li>Kéo EA vào một chart bất kỳ; trong tab Inputs đặt <code>BridgeUrl</code>, <code>AccountId = {row.account_id}</code>, <code>Token</code>{have.hmac ? <>, <code>HmacSecret</code></> : null}.</li>
            <li>Bật AutoTrading chung của terminal để EA chạy. EA chỉ đọc dữ liệu, KHÔNG đặt/sửa/đóng lệnh; nên đăng nhập terminal bằng mật khẩu <b>investor</b>.</li>
            <li>Sau ~1 phút tab Experts báo đã kết nối; tài khoản chuyển “Trực tuyến” trong Khách hàng. Khách vào <code>/c/</code> đăng nhập bằng ID MT + passcode{kind === "create" ? " (hoặc ghép cặp bằng mã ở trên)" : ""}.</li>
          </ol>
        </section>
      )}
    </div>
  );
}
