import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { BellRing, Copy, History, Pencil, Plus, Smartphone, Trash2 } from "lucide-react";
import { Async, Chip, Field, Notice, PageHead, Panel, Sheet, Skeleton, cn } from "../components/ui";
import RuleSheet, { MAX_RULES, MIN_COOLDOWN, serverErrorLines, summarizeCond } from "../components/rulesheet";
import { RuleEventsList, Switch, levelLabel, levelTone } from "../components/notifparts";
import { PermissionCard } from "./Notifications";
import { apiWrite } from "../lib/api";
import { useActiveAccount } from "../lib/account";
import { accountTitle, useAuth } from "../lib/auth";
import { useQuotes, useRuleEvents, useRules, useSymbols } from "../lib/queries";
import { KINDS, OPS, describeRule, useLocalRules } from "../lib/localalerts";
import { dateTime, price, rel } from "../lib/format";
import { useClock } from "../lib/clock";
import { t } from "../lib/i18n";

const CH = (c) => (c === "app" ? t("Trong ứng dụng") : c === "push" ? t("Đẩy") : c);
const MODE = (m) => (m === "once" ? t("Một lần") : t("Mỗi lần chạm lại"));

// ---- Cảnh báo cục bộ (chạy trên thiết bị này; chỉ còn dùng khi máy chủ chưa có hoặc để quản lý cảnh báo cũ) ----
const DEF = { price: "", margin: "200", pl: "5", ea: "10" };
const RANGE = { price: [0, 1e9], margin: [20, 2000], pl: [0.5, 90], ea: [2, 240] };
const LABEL = (k) => (k === "price" ? t("Giá ngưỡng") : k === "margin" ? t("Ngưỡng margin level (%)") : k === "pl" ? t("Ngưỡng lỗ đang mở (% số dư)") : t("Số phút không có dữ liệu"));

function LocalSheet({ init, kind0, accounts, activeId, preSymbol, onClose, onSave }) {
  const edit = !!init;
  const [kind, setKind] = useState(init?.kind || kind0 || "price");
  const [sym, setSym] = useState(init?.symbol || preSymbol || "EURUSD");
  const [op, setOp] = useState(init?.op || "gte");
  const [val, setVal] = useState(init ? String(init.value) : DEF[kind0 || "price"]);
  const [acc, setAcc] = useState(init?.account_id || activeId || accounts[0]?.id || "");
  const [mode, setMode] = useState(init?.mode || (kind0 === "price" || !kind0 ? "once" : "repeat"));
  const symbols = useSymbols();
  const quote = useQuotes(kind === "price" && sym ? [sym.trim().toUpperCase()] : undefined);
  const cur = quote.data?.[0];
  const n = Number(val);
  const [lo, hi] = RANGE[kind];
  const needAcc = kind !== "price";
  const bad = val === "" || Number.isNaN(n) || n < lo || n > hi || (kind === "price" && !/^[A-Za-z0-9:._-]{1,32}$/.test(sym)) || (needAcc && !acc);
  const pickKind = (k) => { setKind(k); if (!edit) setVal(DEF[k]); };
  const submit = (e) => {
    e.preventDefault();
    if (bad) return;
    const s = sym.trim().toUpperCase();
    onSave({ kind, value: n, mode, ...(kind === "price" ? { symbol: s, op } : { account_id: acc }), name: describeRule({ kind, value: n, op, symbol: s }), cooldownMin: kind === "ea" ? 60 : 30 });
  };
  return (
    <Sheet title={edit ? t("Sửa cảnh báo trên thiết bị") : t("Tạo cảnh báo trên thiết bị")} onClose={onClose}>
      <form className="grid gap-3.5" onSubmit={submit} noValidate>
        {!edit && (
          <div className="label"><span>{t("Loại cảnh báo")}</span>
            <div className="seg scroll" role="group" aria-label={t("Loại cảnh báo")}>{Object.entries(KINDS).map(([k, v]) => <button key={k} type="button" aria-pressed={kind === k} onClick={() => pickKind(k)}>{v.label}</button>)}</div></div>
        )}
        <p className="m-0 text-[13px] text-muted">{KINDS[kind].sub}. {t("Báo khi vừa chạm ngưỡng, không báo lặp liên tục.")}</p>
        {kind === "price" && (
          <>
            <Field label={t("Mã")} hint={cur ? t("Giá hiện tại {p}", { p: price(sym.trim().toUpperCase(), cur.bid ?? cur.ask) }) : undefined}>
              <input className="field" list="sym-list" value={sym} onChange={(e) => setSym(e.target.value)} autoCapitalize="characters" />
              <datalist id="sym-list">{(symbols.data || []).slice(0, 80).map((s) => <option key={s.symbol} value={s.symbol}>{s.name}</option>)}</datalist>
            </Field>
            <div className="label"><span>{t("Điều kiện")}</span><div className="seg w-full" role="group" aria-label={t("Điều kiện giá")}>
              {Object.entries(OPS).map(([v, l]) => <button key={v} type="button" className="flex-1" aria-pressed={op === v} onClick={() => setOp(v)}>{v === "gte" ? t("Giá lên tới") : t("Giá xuống tới")}<span className="sr-only"> {l}</span></button>)}</div></div>
          </>
        )}
        {needAcc && accounts.length > 1 && (
          <Field label={t("Tài khoản")}><select className="field" value={acc} onChange={(e) => setAcc(e.target.value)}>{accounts.map((a) => <option key={a.id} value={a.id}>{accountTitle(a)}</option>)}</select></Field>
        )}
        <Field label={LABEL(kind)} error={val !== "" && bad ? t("Nhập số từ {lo} đến {hi}.", { lo, hi }) : null}>
          <input className="field num" inputMode="decimal" value={val} onChange={(e) => setVal(e.target.value)} />
        </Field>
        <div className="label"><span>{t("Số lần báo")}</span><div className="seg w-full" role="group" aria-label={t("Số lần báo")}>
          {[["once", t("Một lần")], ["repeat", t("Mỗi lần chạm lại")]].map(([v, l]) => <button key={v} type="button" className="flex-1" aria-pressed={mode === v} onClick={() => setMode(v)}>{l}</button>)}</div></div>
        <button className="btn primary" type="submit" disabled={bad}>{edit ? t("Lưu thay đổi") : t("Tạo cảnh báo")}</button>
      </form>
    </Sheet>
  );
}

const PRESET_CARDS = () => [
  ["price", t("Giá chạm ngưỡng"), t("Báo khi giá một mã vượt lên hoặc xuống một mức")],
  ["margin", t("Margin thấp"), t("Báo khi mức margin xuống dưới ngưỡng")],
  ["loss", t("Lỗ đang mở lớn"), t("Báo khi lãi/lỗ đang mở xuống dưới −X% số dư")],
  ["drawdown", t("Sụt vốn 24 giờ"), t("Báo khi vốn giảm quá X% so với đỉnh 24 giờ")],
  ["news", t("Tin mạnh sắp ra"), t("Báo trước khi tin tác động cao công bố")],
];

export default function Alerts({ query }) {
  const { acc } = useActiveAccount();
  const { accounts } = useAuth();
  const qc = useQueryClient();
  const now = useClock();
  const lr = useLocalRules();
  const rules = useRules();
  const events = useRuleEvents(null, 30);
  const [sheet, setSheet] = useState(null);   // {init?, dup?, preset?}
  const [lsheet, setLsheet] = useState(null); // {init?, kind0?, preSymbol?}
  const [del, setDel] = useState(null);
  const [ldel, setLdel] = useState(null);
  const [msg, setMsg] = useState(null);       // {tone,text|lines}
  const [busy, setBusy] = useState(false);
  const srv = rules.data?.items || [];
  const srvOk = rules.isSuccess;
  const max = Math.min(rules.data?.limits?.max_rules ?? MAX_RULES, MAX_RULES);
  const full = srv.length >= max;
  const accTitle = useMemo(() => Object.fromEntries(accounts.map((a) => [a.id, accountTitle(a)])), [accounts]);
  useEffect(() => {
    if (!query?.symbol) return;
    if (srvOk) setSheet({ preset: { kind: "price", symbol: query.symbol } }); else if (rules.isError) setLsheet({ kind0: "price", preSymbol: query.symbol });
  }, [query?.symbol, srvOk, rules.isError]); // eslint-disable-line react-hooks/exhaustive-deps
  const refresh = () => qc.invalidateQueries({ queryKey: ["user-rules"] });
  const fail = (e) => setMsg({ tone: "down", lines: serverErrorLines(e) });

  const toggle = async (r, enabled) => {
    setMsg(null); setBusy(true);
    try {
      await apiWrite("PUT", `/user/rules/${r.id}`, { name: r.name, enabled, logic: r.logic, conditions: r.conditions, mode: r.mode, cooldown_min: Math.max(r.cooldown_min ?? 60, MIN_COOLDOWN), expires_at: r.expires_at ?? null, level: r.level, channels: (r.channels || []).filter((c) => c === "app" || c === "push").length ? r.channels.filter((c) => c === "app" || c === "push") : ["app"], note: r.note || "" });
      await refresh();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const remove = async () => { const r = del; setDel(null); setBusy(true); try { await apiWrite("DELETE", `/user/rules/${r.id}`); await refresh(); setMsg({ tone: "up", lines: [t("Đã xoá cảnh báo.")] }); } catch (e) { fail(e); } finally { setBusy(false); } };
  const saved = async () => { const e = sheet?.init && !sheet.dup; await refresh(); setSheet(null); setMsg({ tone: "up", lines: [e ? t("Đã lưu thay đổi.") : t("Đã tạo cảnh báo.")] }); };
  const openCreate = () => (srvOk ? setSheet({}) : setLsheet({}));
  const saveLocal = (data) => { if (lsheet.init) lr.update(lsheet.init.id, data); else lr.add(data); setLsheet(null); };
  const showLocal = lr.rules.length > 0 || rules.isError;

  return (
    <>
      <PageHead title={t("Cảnh báo của tôi")} sub={t("Nhắc bạn khi giá chạm ngưỡng, margin thấp, lỗ đang mở lớn, tin mạnh sắp ra hoặc sụt vốn. Chỉ gửi thông báo, không tự đặt hay đóng lệnh.")}
        right={<button className="btn primary" onClick={openCreate} disabled={srvOk && full}><Plus size={16} aria-hidden="true" /> {t("Tạo cảnh báo")}</button>} />
      <PermissionCard />
      <Notice tone="info" icon={BellRing} title={t("Chọn nơi nhận thông báo")}>
        {t("Mỗi cảnh báo chọn nhận trong ứng dụng và/hoặc thông báo đẩy. Bật thông báo đẩy và quản lý thiết bị ở")} <a className="underline" href="#/thong-bao?tab=settings">{t("Thông báo, mục Cài đặt")}</a>.
      </Notice>
      {msg && <Notice tone={msg.tone}>{(msg.lines || []).length > 1 ? <ul className="m-0 pl-4">{msg.lines.map((l, i) => <li key={i}>{l}</li>)}</ul> : (msg.lines || [])[0]}</Notice>}

      {rules.isPending ? <Skeleton rows={3} h={72} /> : srvOk ? (
        <Panel title={t("Cảnh báo chạy trên máy chủ ({n}/{max})", { n: srv.length, max })} icon={BellRing}>
          {srv.length === 0 ? (
            <div className="grid gap-3"><p className="m-0 text-muted">{t("Bạn chưa tạo cảnh báo nào. Chọn một mẫu để bắt đầu:")}</p>
              <div className="grid gap-2 sm:grid-cols-2">{PRESET_CARDS().map(([k, l, s]) => (
                <button key={k} type="button" className="pos-card text-left cursor-pointer text-inherit font-[inherit] min-h-[64px]" onClick={() => setSheet({ preset: { kind: k } })}><b>{l}</b><span className="text-[12.5px] text-muted">{s}</span></button>))}</div></div>
          ) : (
            <ul className="list-none m-0 p-0 grid gap-2.5">
              {srv.map((r) => {
                const expired = r.expires_at && new Date(r.expires_at).getTime() < now;
                const accs = [...new Set((r.conditions || []).filter((c) => c.type === "account" && c.account_id).map((c) => c.account_id))];
                return (
                  <li key={r.id} className={cn("rounded-xl border border-line bg-panel2 p-3 grid gap-2", !r.enabled && "opacity-85")}>
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="font-semibold break-words">{r.name}</div>
                        <div className="flex flex-wrap gap-1 mt-1">
                          <Chip tone={levelTone(r.level)}>{levelLabel(r.level)}</Chip>
                          <Chip tone={r.enabled && !expired ? "up" : ""}>{expired ? t("Đã hết hạn") : r.enabled ? t("Đang bật") : r.mode === "once" && r.fire_count > 0 ? t("Đã báo, đã tắt") : t("Đã tắt")}</Chip>
                          <Chip>{MODE(r.mode)}</Chip>
                          {(r.channels || []).filter((c) => c === "app" || c === "push").map((c) => <Chip key={c}>{CH(c)}</Chip>)}
                          {accs.map((a) => <Chip key={a}>{accTitle[a] || a}</Chip>)}
                        </div>
                      </div>
                      <Switch on={!!r.enabled} disabled={busy} onChange={(v) => toggle(r, v)} label={r.enabled ? t("Tắt cảnh báo {name}", { name: r.name }) : t("Bật cảnh báo {name}", { name: r.name })} />
                    </div>
                    <ul className="m-0 pl-4 text-[13px]">{(r.conditions || []).map((c, i) => <li key={i} className="break-words">{summarizeCond(c)}</li>)}</ul>
                    <div className="text-[12px] text-faint">
                      {t("Kích hoạt gần nhất: {a}", { a: r.last_fired_at ? rel(r.last_fired_at) : t("chưa") })} · {t("{n} lần", { n: r.fire_count ?? 0 })}
                      {r.mode === "repeat" ? ` · ${t("chờ {m} phút giữa hai lần", { m: r.cooldown_min })}` : ""}
                      {r.expires_at ? ` · ${t("hết hạn {d}", { d: dateTime(r.expires_at) })}` : ""}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button className="btn sm" disabled={busy} onClick={() => setSheet({ init: r })} aria-label={t("Sửa cảnh báo {name}", { name: r.name })}><Pencil size={15} aria-hidden="true" /> {t("Sửa")}</button>
                      <button className="btn sm" disabled={busy || full} onClick={() => setSheet({ init: r, dup: true })} aria-label={t("Nhân bản cảnh báo {name}", { name: r.name })} title={full ? t("Đã đủ số cảnh báo tối đa") : undefined}><Copy size={15} aria-hidden="true" /> {t("Nhân bản")}</button>
                      <button className="btn sm danger ml-auto" disabled={busy} onClick={() => setDel(r)} aria-label={t("Xoá cảnh báo {name}", { name: r.name })}><Trash2 size={15} aria-hidden="true" /> {t("Xoá")}</button>
                    </div>
                  </li>);
              })}
            </ul>
          )}
        </Panel>
      ) : (
        <Notice tone="info" icon={Smartphone} title={t("Cảnh báo trên máy chủ chưa khả dụng")}>
          {t("Hiện chỉ dùng được cảnh báo chạy trên thiết bị này (khi ứng dụng đang mở, kể cả tab nền).")} {rules.error?.message}
        </Notice>
      )}

      {showLocal && (
        <Panel title={t("Cảnh báo chạy trên thiết bị này ({n})", { n: lr.rules.length })} icon={Smartphone}
          right={!srvOk ? <button className="btn sm" onClick={() => setLsheet({})}><Plus size={15} aria-hidden="true" /> {t("Thêm")}</button> : null}>
          {srvOk && <p className="m-0 mb-2.5 text-[12.5px] text-muted">{t("Cảnh báo cũ chỉ kiểm tra khi ứng dụng đang mở. Nên tạo lại ở danh sách trên để nhận cả khi đã đóng ứng dụng.")}</p>}
          {lr.rules.length === 0 ? (
            <div className="grid gap-3"><p className="m-0 text-muted">{t("Bạn chưa tạo cảnh báo nào.")}</p>
              <div className="grid gap-2 sm:grid-cols-2">{Object.entries(KINDS).map(([k, v]) => (
                <button key={k} type="button" className="pos-card text-left cursor-pointer text-inherit font-[inherit] min-h-[64px]" onClick={() => setLsheet({ kind0: k })}><b>{v.label}</b><span className="text-[12.5px] text-muted">{v.sub}</span></button>))}</div></div>
          ) : (
            <ul className="list-none m-0 p-0 grid gap-2.5">
              {lr.rules.map((r) => (
                <li key={r.id} className={cn("rounded-xl border border-line bg-panel2 p-3 grid gap-1.5", !r.enabled && "opacity-80")}>
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1"><div className="font-semibold break-words">{describeRule(r)}</div>
                      <div className="flex flex-wrap gap-1 mt-1"><Chip>{KINDS[r.kind]?.label}</Chip><Chip tone={r.enabled ? "up" : ""}>{r.enabled ? t("Đang bật") : r.mode === "once" && r.lastFired ? t("Đã báo") : t("Đã tắt")}</Chip><Chip>{MODE(r.mode)}</Chip>{r.account_id && <Chip>{accTitle[r.account_id] || r.account_id}</Chip>}</div></div>
                    <Switch on={!!r.enabled} onChange={(v) => lr.update(r.id, { enabled: v })} label={r.enabled ? t("Tắt cảnh báo {name}", { name: describeRule(r) }) : t("Bật cảnh báo {name}", { name: describeRule(r) })} />
                  </div>
                  <div className="flex items-center gap-2"><button className="btn sm" onClick={() => setLsheet({ init: r })} aria-label={t("Sửa cảnh báo {name}", { name: describeRule(r) })}><Pencil size={15} aria-hidden="true" /> {t("Sửa")}</button>
                    <button className="btn sm danger ml-auto" onClick={() => setLdel(r)} aria-label={t("Xoá cảnh báo {name}", { name: describeRule(r) })}><Trash2 size={15} aria-hidden="true" /> {t("Xoá")}</button></div>
                </li>))}
            </ul>
          )}
        </Panel>
      )}

      {events.isSuccess && (
        <Panel title={t("Lịch sử kích hoạt từ máy chủ")} icon={History} right={<a className="btn sm" href="#/thong-bao?tab=history">{t("Xem tất cả")}</a>}>
          <Async q={events} rows={3} isEmpty={(d) => !(d?.items || []).length} empty={t("Chưa có cảnh báo nào được kích hoạt.")}>
            {(d) => <RuleEventsList items={d.items.slice(0, 8)} />}
          </Async>
        </Panel>
      )}

      {sheet && <RuleSheet init={sheet.init} dup={sheet.dup} preset={sheet.preset} accounts={accounts} activeId={acc?.id} count={srv.length} onClose={() => setSheet(null)} onSaved={saved} />}
      {lsheet && <LocalSheet init={lsheet.init} kind0={lsheet.kind0} preSymbol={lsheet.preSymbol} accounts={accounts} activeId={acc?.id} onClose={() => setLsheet(null)} onSave={saveLocal} />}
      {ldel && (
        <Sheet title={t("Xoá cảnh báo?")} onClose={() => setLdel(null)}>
          <p className="m-0 mb-3 text-[14px]">{t("Cảnh báo {name} sẽ bị xoá.", { name: describeRule(ldel) })}</p>
          <div className="flex gap-2"><button className="btn danger" onClick={() => { lr.remove(ldel.id); setLdel(null); }}>{t("Xoá")}</button><button className="btn" onClick={() => setLdel(null)}>{t("Giữ lại")}</button></div>
        </Sheet>
      )}
      {del && (
        <Sheet title={t("Xoá cảnh báo trên máy chủ?")} onClose={() => setDel(null)}>
          <p className="m-0 mb-3 text-[14px]">{t("Cảnh báo {name} sẽ bị xoá và không thể khôi phục.", { name: del.name })}</p>
          <div className="flex gap-2"><button className="btn danger" onClick={remove}>{t("Xoá")}</button><button className="btn" onClick={() => setDel(null)}>{t("Giữ lại")}</button></div>
        </Sheet>
      )}
    </>
  );
}
