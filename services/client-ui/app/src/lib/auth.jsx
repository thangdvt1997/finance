import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, auth, resetCsrf } from "./api";
import { lget, lset } from "./lstore";
import { clearPersisted } from "./persist";
import { clearNotifications } from "./notifstore";
import { t } from "./i18n";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

/** "mt5:12345678" -> { id, platform: "mt5", login: "12345678" } (chấp nhận cả object từ máy chủ). */
export function normAccount(a) {
  if (!a) return null;
  const o = typeof a === "string" ? { account_id: a } : a;
  const id = o.account_id || o.id;
  const m = /^(mt[45]):(.+)$/i.exec(id || "");
  return {
    id, platform: (o.platform || m?.[1] || "").toLowerCase(), login: String(o.login ?? m?.[2] ?? ""),
    server: o.server || "", label: o.label || "", status: o.status || "active", lastSeen: o.last_seen_at || null,
  };
}
export const accountTitle = (a) => (a ? `${a.platform.toUpperCase()} · ${a.login}` : "—");

const normMe = (m) => ({
  userId: m.user_id, role: m.role, name: m.display_name || "", mustChange: !!m.must_change_password,
  accounts: (m.accounts || []).map(normAccount).filter((a) => a?.id),
});

export function AuthProvider({ children }) {
  const qc = useQueryClient();
  const [state, setState] = useState({ status: "loading", me: null, error: null });
  const [activeId, setActiveId] = useState(() => lget("tc-acct", ""));

  const refresh = useCallback(async () => {
    try {
      const m = await auth("GET", "/me");
      setState({ status: "authed", me: normMe(m), error: null });
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setState({ status: "anon", me: null, error: null });
      else setState({ status: "down", me: null, error: e.message || t("Không kiểm tra được phiên đăng nhập.") });
      return false;
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    const h = () => { qc.clear(); clearPersisted(); resetCsrf(); setState({ status: "anon", me: null, error: null }); };
    addEventListener("tc-unauth", h);
    return () => removeEventListener("tc-unauth", h);
  }, [qc]);

  const accounts = state.me?.accounts || [];
  const active = accounts.find((a) => a.id === activeId) || accounts[0] || null;
  const pick = useCallback((id) => { setActiveId(id); lset("tc-acct", id); }, []);

  const api = useMemo(() => ({
    ...state, accounts, active, pick, refresh,
    async login(platform, login, secret, server) {
      await auth("POST", "/login", { platform, login: String(login).trim(), secret, ...(server?.trim() ? { server: server.trim() } : {}) });
      qc.clear();
      await refresh();
    },
    async pair(platform, login, pairing_code, new_password, server) {
      const sv = server?.trim() ? { server: server.trim() } : {};
      await auth("POST", "/pair", { platform, login: String(login).trim(), pairing_code: pairing_code.trim(), new_password, ...sv });
      await auth("POST", "/login", { platform, login: String(login).trim(), secret: new_password, ...sv }); // ghép cặp xong chưa có phiên -> đăng nhập luôn
      qc.clear();
      await refresh();
    },
    async changePassword(current_password, new_password) {
      await auth("POST", "/change-password", { current_password, new_password });
      await refresh();
    },
    async logout(all = false) {
      try { await auth("POST", all ? "/logout-all" : "/logout", {}); } catch { /* vẫn xoá phía máy khách */ }
      qc.clear(); clearPersisted(); clearNotifications(); resetCsrf();
      setState({ status: "anon", me: null, error: null });
    },
  }), [state, accounts, active, pick, refresh, qc]);

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}
