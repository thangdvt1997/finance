import { useEffect, useState } from "react";
import { Eye, EyeOff, ShieldCheck } from "lucide-react";
import { ApiError, detailText } from "../lib/api";
import { Field, Notice, Seg } from "./ui";
import { t } from "../lib/i18n";

export const PLATFORMS = [{ value: "mt5", label: "MT5" }, { value: "mt4", label: "MT4" }];
export const PW_MIN = 10;

export const TradingPwWarning = () => (
  <>{t("Mật khẩu cổng là mật khẩu riêng của ứng dụng này.")} <b>{t("Đừng nhập mật khẩu giao dịch hoặc mật khẩu investor của MT")}</b> {t("ở bất kỳ ô nào, chúng tôi không bao giờ cần đến chúng.")}</>
);

export function PlatformPick({ value, onChange }) {
  return (
    <div className="label"><span id="plat-l">{t("Nền tảng")}</span>
      <Seg value={value} onChange={onChange} options={PLATFORMS} label={t("Nền tảng giao dịch")} className="w-full [&>button]:flex-1" />
    </div>
  );
}

export function PasswordInput({ id, value, onChange, autoComplete, placeholder, invalid, describedBy, required = true }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input id={id} className="field !pr-12" type={show ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)} autoComplete={autoComplete}
        placeholder={placeholder} required={required} aria-invalid={invalid || undefined} aria-describedby={describedBy} autoCapitalize="none" autoCorrect="off" spellCheck={false} />
      <button type="button" className="ibtn absolute right-0 top-0" onClick={() => setShow((s) => !s)} aria-label={show ? t("Ẩn mật khẩu") : t("Hiện mật khẩu")} aria-pressed={show}>
        {show ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
      </button>
    </div>
  );
}

/** Độ mạnh mật khẩu đơn giản: độ dài + độ đa dạng ký tự. Không thay thế kiểm tra của máy chủ. */
export function pwScore(p) {
  let s = 0;
  if (p.length >= PW_MIN) s++;
  if (p.length >= 14) s++;
  if (/[a-z]/.test(p) && /[A-Z]/.test(p)) s++;
  if (/\d/.test(p) && /[^A-Za-z0-9]/.test(p)) s++;
  return Math.min(s, 4);
}
export function PwStrength({ value }) {
  if (!value) return null;
  const s = pwScore(value);
  const L = [t("Rất yếu"), t("Yếu"), t("Tạm được"), t("Tốt"), t("Mạnh")][value.length < PW_MIN ? 0 : s];
  const col = s >= 3 ? "var(--up)" : s === 2 ? "var(--accent)" : "var(--down)";
  return (
    <div className="grid gap-1" aria-live="polite">
      <div className="flex gap-1" aria-hidden="true">{[0, 1, 2, 3].map((i) => <i key={i} className="h-[5px] flex-1 rounded" style={{ background: i < s && value.length >= PW_MIN ? col : "var(--line2)" }} />)}</div>
      <span className="text-[12px] text-muted">{t("Độ mạnh: {L}. Tối thiểu {n} ký tự; nên trộn chữ hoa, thường, số và ký hiệu.", { L, n: PW_MIN })}</span>
    </div>
  );
}

/** Lỗi xác thực -> thông điệp người dùng (chung chung, không lộ tài khoản có tồn tại hay không). */
export function authError(e, ctx = "login") {
  if (!(e instanceof ApiError)) return { text: t("Có lỗi không xác định. Thử lại."), kind: "err" };
  const d = detailText(e.detail).toLowerCase();
  if (e.status === 423 || /lock|khoá|khoa/.test(d)) return { text: t("Tài khoản đang bị khoá tạm do nhập sai nhiều lần."), kind: "lock", wait: e.retryAfter };
  if (e.status === 429) return { text: t("Quá nhiều lần thử. Vui lòng chờ rồi thử lại."), kind: "lock", wait: e.retryAfter || 30 };
  if (e.status === 0 || e.status === 502 || e.status === 503 || e.status === 504) return { text: t("Dịch vụ đăng nhập chưa sẵn sàng. Thử lại sau ít phút."), kind: "down" };
  if (/pair|ghép/.test(d) && ctx === "login") return { text: t("Tài khoản này chưa được ghép cặp. Chuyển sang tab \"Ghép cặp lần đầu\"."), kind: "pair" };
  if (e.status === 401) return { text: ctx === "login" ? t("Số tài khoản hoặc mật khẩu cổng không đúng.") : t("Mã ghép cặp không đúng hoặc đã hết hạn."), kind: "err" };
  if (e.status === 422 || e.status === 400) return { text: detailText(e.detail) || t("Thông tin chưa hợp lệ."), kind: "err" };
  return { text: e.message, kind: "err" };
}

/** Đếm ngược thời gian khoá tạm. */
export function LockNotice({ wait, onDone }) {
  const [left, setLeft] = useState(Math.max(0, Math.round(wait || 0)));
  useEffect(() => {
    if (!left) return;
    const iv = setInterval(() => setLeft((l) => { if (l <= 1) { onDone?.(); return 0; } return l - 1; }), 1000);
    return () => clearInterval(iv);
  }, [left > 0]); // eslint-disable-line react-hooks/exhaustive-deps
  const mm = String(Math.floor(left / 60)).padStart(2, "0"), ss = String(left % 60).padStart(2, "0");
  return (
    <Notice tone="warn" title={t("Tạm khoá để bảo vệ tài khoản")}>
      {t("Nhập sai nhiều lần nên đăng nhập bị khoá tạm thời.")}{left > 0 ? <> {t("Thử lại sau")} <b className="num text-fg">{mm}:{ss}</b>.</> : ` ${t("Bạn có thể thử lại.")}`} {t("Nếu bạn quên mật khẩu cổng, hãy liên hệ quản trị viên để được cấp mã ghép cặp mới.")}
    </Notice>
  );
}

export function PrivacyLine() {
  return (
    <p className="m-0 flex items-start gap-2 text-[12.5px] text-muted">
      <ShieldCheck size={16} className="shrink-0 mt-[2px] text-up" aria-hidden="true" />
      <span>{t("Ứng dụng chỉ theo dõi và phân tích tài khoản của bạn. Không đặt, sửa hay đóng lệnh.")}</span>
    </p>
  );
}

export { Field, Notice };
