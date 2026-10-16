import { useState } from "react";
import { KeyRound } from "lucide-react";
import { useAuth } from "../lib/auth";
import { Field, Notice } from "./ui";
import { PasswordInput, PwStrength, PW_MIN, TradingPwWarning, authError } from "./authparts";
import { t } from "../lib/i18n";

/** Đổi mật khẩu cổng. `forced` = bắt buộc đổi (lần đầu / sau khi quản trị cấp lại). */
export default function ChangePasswordForm({ forced, onDone }) {
  const a = useAuth();
  const [cur, setCur] = useState("");
  const [p1, setP1] = useState("");
  const [p2, setP2] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const valid = cur.length > 0 && p1.length >= PW_MIN && p1 === p2 && p1 !== cur;
  const submit = async (e) => {
    e.preventDefault();
    if (!valid || busy) return;
    setBusy(true); setMsg(null);
    try {
      await a.changePassword(cur, p1);
      setCur(""); setP1(""); setP2("");
      setMsg({ ok: true, text: t("Đã đổi mật khẩu cổng.") });
      onDone?.();
    } catch (ex) {
      const r = authError(ex, "change");
      setMsg({ ok: false, text: ex.status === 401 || ex.status === 403 ? t("Mật khẩu hiện tại không đúng.") : r.text });
    } finally { setBusy(false); }
  };
  return (
    <form className="grid gap-3.5" onSubmit={submit} noValidate>
      {forced && <Notice tone="warn" title={t("Cần đổi mật khẩu cổng")}>{t("Để bảo mật, bạn phải đặt mật khẩu cổng mới trước khi tiếp tục.")}</Notice>}
      <Field label={t("Mật khẩu cổng hiện tại")}><PasswordInput value={cur} onChange={setCur} autoComplete="current-password" /></Field>
      <Field label={t("Mật khẩu cổng mới")} error={p1 && p1 === cur ? t("Mật khẩu mới phải khác mật khẩu hiện tại.") : null}><PasswordInput value={p1} onChange={setP1} autoComplete="new-password" /></Field>
      <PwStrength value={p1} />
      <Field label={t("Nhập lại mật khẩu mới")} error={p2 && p1 !== p2 ? t("Hai mật khẩu chưa khớp.") : null}><PasswordInput value={p2} onChange={setP2} autoComplete="new-password" invalid={!!p2 && p1 !== p2} /></Field>
      <Notice tone="info" icon={KeyRound}><TradingPwWarning /></Notice>
      {msg && <Notice tone={msg.ok ? "up" : "down"}>{msg.text}</Notice>}
      <button className="btn primary self-start" type="submit" disabled={!valid || busy} aria-busy={busy}>{busy ? t("Đang lưu…") : t("Đổi mật khẩu")}</button>
    </form>
  );
}
