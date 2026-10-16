// Trình hướng dẫn bật TOTP (xác thực hai bước) cho master/nhân sự: tạo secret -> QR + secret chữ -> nhập mã 6 số -> xong.
// Secret chỉ nằm trong state của hộp thoại (KHÔNG localStorage/sessionStorage/URL). QR vẽ trong trình duyệt bằng qrcode-generator (MIT, tệp vendor, nạp lười).
import { useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, KeyRound, ScanLine, ShieldCheck, Smartphone } from "lucide-react";
import { Dialog } from "../dialog";
import { authPost } from "../../lib/fleetApi";
import { useAuthMe } from "../../lib/fleetQueries";
import { Banner, CopyBtn, ErrLine, PRIMARY } from "./bits";

function QrSvg({ uri }) {
  const [svg, setSvg] = useState(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let live = true;
    import("../../vendor/qrcode-generator").then((m) => {
      const qr = m.default(0, "M");
      qr.addData(uri);
      qr.make();
      if (live) setSvg(qr.createSvgTag({ cellSize: 5, margin: 3, scalable: true, alt: "Mã QR để quét bằng ứng dụng xác thực", title: "Mã QR TOTP" }));
    }).catch(() => live && setErr(true));
    return () => { live = false; };
  }, [uri]);
  if (err) return <p className="m-0 text-[12.5px] text-muted">Không vẽ được mã QR — dùng chuỗi bí mật bên dưới để nhập tay vào ứng dụng xác thực.</p>;
  if (!svg) return <div className="skel" style={{ width: 200, height: 200 }} aria-label="Đang tạo mã QR" />;
  // svg do thư viện sinh ra từ otpauth_uri (chỉ có path/rect), nền trắng cố định để quét được ở giao diện tối
  return <div className="rounded-md bg-white p-1 inline-block" style={{ width: 208, height: 208 }} dangerouslySetInnerHTML={{ __html: svg }} />;
}

export default function TotpWizard({ open, onClose }) {
  const qc = useQueryClient();
  const me = useAuthMe();
  const [step, setStep] = useState(1);           // 1 giới thiệu · 2 quét + nhập mã · 3 xong
  const [sec, setSec] = useState(null);          // {secret, otpauth_uri}
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const input = useRef(null);
  const enabled = !!me.data?.totp_enabled;

  useEffect(() => { if (open) { setStep(enabled ? 3 : 1); setSec(null); setCode(""); setErr(null); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (step === 2) setTimeout(() => input.current?.focus(), 50); }, [step]);

  const grouped = useMemo(() => (sec?.secret || "").replace(/(.{4})/g, "$1 ").trim(), [sec]);

  const gen = async () => {
    setBusy(true); setErr(null);
    try { setSec(await authPost("/totp/setup")); setStep(2); } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  const confirm = async (e) => {
    e?.preventDefault();
    if (!/^\d{6}$/.test(code)) { setErr({ message: "Nhập đúng 6 chữ số hiện trong ứng dụng xác thực." }); return; }
    setBusy(true); setErr(null);
    try {
      await authPost("/totp/enable", { code });
      setSec(null); setStep(3);
      qc.invalidateQueries({ queryKey: ["me"] });
    } catch (e2) {
      setErr({ message: e2.status === 400 || e2.status === 401 || e2.status === 403 ? "Mã không đúng hoặc đã hết hạn. Đợi mã mới (30 giây) rồi nhập lại." : e2.message });
      setCode("");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onClose={onClose} title="Bật xác thực hai bước (TOTP)" description="Bắt buộc cho master trước khi dùng thao tác nhạy cảm: thao tác hàng loạt, nhập CSV, quản lý vai trò, xem như khách."
      footer={step === 3 ? <button className={`btn ${PRIMARY}`} onClick={onClose}>Đóng</button> : <button className="btn" onClick={onClose}>Để sau</button>}>
      <div className="p-3 grid gap-3">
        <ol className="m-0 p-0 list-none flex flex-wrap gap-2 text-[12px]" aria-label="Các bước">
          {["Chuẩn bị", "Quét mã & xác nhận", "Hoàn tất"].map((t, i) => (
            <li key={t} aria-current={step === i + 1 ? "step" : undefined} className={`fl-pill ${step === i + 1 ? "t-warn" : step > i + 1 ? "t-ok" : "t-mute"}`}>{i + 1}. {t}</li>
          ))}
        </ol>
        {step === 1 && (
          <div className="grid gap-3">
            <p className="m-0 text-[13px]">Bạn cần một ứng dụng xác thực trên điện thoại (Google Authenticator, Microsoft Authenticator, Authy, 1Password…). Sau khi bật, mỗi lần đăng nhập sẽ hỏi thêm mã 6 số đổi mỗi 30 giây.</p>
            <ul className="m-0 pl-5 text-[12.5px] text-muted grid gap-1">
              <li>Bước 1: Bấm “Tạo mã QR” bên dưới.</li>
              <li>Bước 2: Mở ứng dụng xác thực → thêm tài khoản → quét QR (hoặc nhập chuỗi bí mật).</li>
              <li>Bước 3: Nhập mã 6 số đang hiện để xác nhận.</li>
            </ul>
            <ErrLine error={err} />
            <div><button className={`btn ${PRIMARY}`} onClick={gen} disabled={busy}><ScanLine size={14} aria-hidden="true" />{busy ? "Đang tạo…" : "Tạo mã QR"}</button></div>
          </div>
        )}
        {step === 2 && sec && (
          <form onSubmit={confirm} className="grid gap-3">
            <div className="flex flex-wrap gap-4 items-start">
              <QrSvg uri={sec.otpauth_uri} />
              <div className="grid gap-2 min-w-0 flex-1 basis-56">
                <p className="m-0 text-[12.5px] text-muted flex items-start gap-1.5"><Smartphone size={14} className="shrink-0 mt-[2px]" aria-hidden="true" />Không quét được? Nhập tay chuỗi bí mật (loại “theo thời gian”):</p>
                <div className="fl-secret"><span className="fl-secret-k">Chuỗi bí mật (chỉ hiện lúc này)</span><span className="fl-secret-v" tabIndex={0}>{grouped}</span><CopyBtn text={sec.secret} small /></div>
                <Banner tone="warn" title="Không chia sẻ mã QR/chuỗi này">Ai có chuỗi này vượt được lớp xác thực thứ hai của bạn. Đóng hộp thoại là không xem lại được — nếu lỡ, bấm “Tạo mã QR” lại để lấy chuỗi mới.</Banner>
              </div>
            </div>
            <div className="fl-field">
              <label htmlFor="totp-code">Mã 6 số trong ứng dụng xác thực</label>
              <input ref={input} id="totp-code" className="field num" style={{ maxWidth: 180, letterSpacing: ".25em", fontSize: 16 }} inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="000000" aria-describedby="totp-hint" />
              <span id="totp-hint" className="fl-help">Mỗi mã chỉ dùng được một lần; nếu báo sai, đợi mã kế tiếp.</span>
            </div>
            <ErrLine error={err} />
            <div className="flex flex-wrap gap-2"><button type="submit" className={`btn ${PRIMARY}`} disabled={busy || code.length !== 6}><KeyRound size={14} aria-hidden="true" />{busy ? "Đang xác nhận…" : "Xác nhận & bật TOTP"}</button>
              <button type="button" className="btn" onClick={gen} disabled={busy}>Tạo lại mã mới</button></div>
          </form>
        )}
        {step === 3 && (
          <div className="grid gap-2">
            <Banner tone="ok" icon={CheckCircle2} title="Đã bật xác thực hai bước">Từ lần đăng nhập sau, nhập thêm mã 6 số. Các thao tác nhạy cảm (hàng loạt, nhập CSV, vai trò, xem như khách) đã được mở.</Banner>
            <p className="m-0 text-[12.5px] text-muted flex items-center gap-1.5"><ShieldCheck size={14} aria-hidden="true" />Mất điện thoại? Chạy <code>auth_bootstrap_master.sh --reset</code> trên máy chủ để đặt lại (xem docs/AUTH.md).</p>
          </div>
        )}
      </div>
    </Dialog>
  );
}
