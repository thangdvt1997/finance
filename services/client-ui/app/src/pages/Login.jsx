import { useState } from "react";
import { KeyRound, LogIn, Link2 } from "lucide-react";
import { MOCK } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Chip, Field, Notice, Seg } from "../components/ui";
import { LockNotice, PasswordInput, PlatformPick, PrivacyLine, PwStrength, PW_MIN, TradingPwWarning, authError } from "../components/authparts";
import { Brand } from "../components/shell";
import { LANGS, t } from "../lib/i18n";
import { usePrefs } from "../lib/prefs";

const modes = () => [{ value: "login", label: t("Đăng nhập") }, { value: "pair", label: t("Ghép cặp lần đầu") }];

export default function Login() {
  const a = useAuth();
  const { prefs, set: setPref } = usePrefs();
  const [mode, setMode] = useState("login");
  const [platform, setPlatform] = useState("mt5");
  const [login, setLogin] = useState("");
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [server, setServer] = useState("");
  const [pw1, setPw1] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const loginOk = /^\d{4,12}$/.test(login.trim());
  const valid = mode === "login"
    ? loginOk && secret.length > 0
    : loginOk && code.trim().length >= 4 && pw1.length >= PW_MIN && pw1 === pw2;

  const submit = async (e) => {
    e.preventDefault();
    if (busy || !valid) return;
    setBusy(true); setErr(null);
    try {
      if (mode === "login") await a.login(platform, login, secret, server);
      else await a.pair(platform, login, code, pw1, server);
      setSecret(""); setPw1(""); setPw2(""); setCode("");
    } catch (ex) {
      const r = authError(ex, mode);
      setErr(r);
      if (r.kind === "pair") setMode("pair");
      setSecret("");
    } finally { setBusy(false); }
  };
  const switchMode = (m) => { setMode(m); setErr(null); };

  return (
    <main className="auth-wrap" id="main">
      <div className="auth-card rise">
        <div className="flex items-center gap-3"><Brand /><div className="min-w-0"><h1 className="m-0 text-[20px] font-bold tracking-tight">{t("Tài khoản của tôi")}</h1><div className="text-[13px] text-muted">{t("Theo dõi tài khoản MT4/MT5 của bạn")}</div></div></div>

        {MOCK && <Notice tone="warn" title={t("Chế độ dữ liệu mẫu")}>{t("Đang dùng dữ liệu giả để xem giao diện. Thử:")} MT5 · <span className="num">12345678</span> · {t("mật khẩu")} <span className="num">demo-cong-1</span>. {t("Ghép cặp:")} MT4 · <span className="num">55555555</span> · {t("mã")} <span className="num">PAIR-2468</span>.</Notice>}

        <form className="panel panel-b grid gap-3.5" onSubmit={submit} noValidate>
          <Seg value={mode} onChange={switchMode} options={modes()} label={t("Chọn chế độ")} className="w-full [&>button]:flex-1" />
          <PlatformPick value={platform} onChange={setPlatform} />
          <Field label={t("Số tài khoản MT")} hint={t("Số login hiển thị ở góc trên cửa sổ MT4/MT5 của bạn.")} error={login && !loginOk ? t("Số tài khoản gồm 4 đến 12 chữ số.") : null}>
            <input className="field num" inputMode="numeric" pattern="[0-9]*" autoComplete="username" value={login} onChange={(e) => setLogin(e.target.value.replace(/\s/g, ""))}
              placeholder={t("vd: 12345678")} required aria-invalid={login && !loginOk ? true : undefined} />
          </Field>

          <details className="text-[13px]">
            <summary className="min-h-[44px] flex items-center cursor-pointer text-muted">{t("Số tài khoản trùng ở nhiều broker? Nhập máy chủ")}</summary>
            <Field label={t("Máy chủ broker (tuỳ chọn)")} hint={t("Chỉ cần khi hệ thống yêu cầu, ví dụ ICMarketsSC-Live01.")}><input className="field" value={server} onChange={(e) => setServer(e.target.value)} autoCapitalize="none" spellCheck={false} /></Field>
          </details>

          {mode === "login" ? (
            <Field label={t("Mật khẩu cổng")} hint={t("Mật khẩu do quản trị cấp hoặc bạn tự đặt khi ghép cặp.")}>
              <PasswordInput value={secret} onChange={setSecret} autoComplete="current-password" />
            </Field>
          ) : (
            <>
              <Notice tone="info" icon={Link2} title={t("Lần đầu sử dụng")}>
                {t("Nhập mã ghép cặp hiển thị trong tab")} <b>Experts</b> {t("của MT (khi gắn EA lên biểu đồ) hoặc do quản trị viên gửi, rồi tự đặt mật khẩu cổng cho riêng bạn.")}
              </Notice>
              <Field label={t("Mã ghép cặp")}>
                <input className="field num" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" autoCapitalize="characters" spellCheck={false} placeholder={t("vd: PAIR-2468")} required />
              </Field>
              <Field label={t("Mật khẩu cổng mới")}><PasswordInput value={pw1} onChange={setPw1} autoComplete="new-password" /></Field>
              <PwStrength value={pw1} />
              <Field label={t("Nhập lại mật khẩu cổng")} error={pw2 && pw1 !== pw2 ? t("Hai mật khẩu chưa khớp.") : null}><PasswordInput value={pw2} onChange={setPw2} autoComplete="new-password" invalid={!!pw2 && pw1 !== pw2} /></Field>
            </>
          )}

          <Notice tone="warn" icon={KeyRound}><TradingPwWarning /></Notice>

          {err?.kind === "lock" ? <LockNotice wait={err.wait} onDone={() => setErr(null)} />
            : err && <Notice tone="down">{err.text}</Notice>}

          <button className="btn primary" type="submit" disabled={busy || !valid} aria-busy={busy}>
            {mode === "login" ? <LogIn size={17} aria-hidden="true" /> : <Link2 size={17} aria-hidden="true" />}
            {busy ? t("Đang xử lý…") : mode === "login" ? t("Đăng nhập") : t("Ghép cặp và đăng nhập")}
          </button>
        </form>

        <PrivacyLine />
        <div className="flex flex-wrap gap-2"><Chip tone="info">{t("Chỉ theo dõi, không đặt lệnh")}</Chip><Chip>{t("Dữ liệu chỉ của riêng bạn")}</Chip></div>
        <div className="flex items-center justify-between gap-3 flex-wrap"><span className="text-[12.5px] text-muted">{t("Ngôn ngữ")}</span><Seg value={prefs.lang} onChange={(v) => setPref({ lang: v })} options={LANGS} label={t("Chọn ngôn ngữ")} /></div>
      </div>
    </main>
  );
}
