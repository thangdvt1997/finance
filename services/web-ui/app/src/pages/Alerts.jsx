import { useCallback, useEffect, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { Bell } from "lucide-react";
import { Async, Chip, Loadmore, PageHead, Panel, Seg } from "../components/ui";
import { EventsTab, RulesTab } from "../components/rules";
import { useAlerts } from "../lib/queries";
import { dateTime, rel, clean } from "../lib/format";

const LV = { crit: ["Nghiêm trọng", "down"], warn: ["Cảnh báo", "accent"], info: ["Thông tin", ""] };

/** Cảnh báo hệ thống (alert-service) — giữ nguyên giao diện cũ. */
function SystemAlerts() {
  const [level, setLevel] = useState("");
  const [limit, setLimit] = useState(50);
  const q = useAlerts({ level: level || undefined, limit });
  return (
    <Panel title="Lịch sử cảnh báo hệ thống" icon={Bell} pad={false} fill bodyClass="flex flex-col"
      right={<Seg value={level} onChange={(v) => { setLevel(v); setLimit(50); }} label="Lọc theo mức"
        options={[{ value: "", label: "Tất cả" }, { value: "crit", label: "Nghiêm trọng" }, { value: "warn", label: "Cảnh báo" }, { value: "info", label: "Thông tin" }]} />}>
      <div className="p-3 scroll-y">
        <Async q={q} rows={6} empty="Chưa có cảnh báo ở mức này.">
          {(d) => (
            <>
              <ul className="m-0 p-0 list-none grid grid-cols-[repeat(auto-fill,minmax(min(100%,30rem),1fr))] gap-3">
                {d.items.map((a) => (
                  <li key={a.id} className="rounded-md border border-line bg-panel2 p-3 grid gap-1 content-start sm:grid-cols-[130px_1fr] sm:gap-4">
                    <div className="flex sm:flex-col items-center sm:items-start gap-2 sm:gap-1">
                      <Chip tone={LV[a.level]?.[1]}>{LV[a.level]?.[0] || a.level}</Chip>
                      <span className="text-[11.5px] text-faint" title={a.ts}>{dateTime(a.ts)} · {rel(a.ts)}</span>
                    </div>
                    <div className="min-w-0">
                      <div className="font-semibold">{clean(a.title)}</div>
                      {a.body && <p className="m-0 text-muted whitespace-pre-line">{clean(a.body)}</p>}
                      <div className="flex flex-wrap gap-1 mt-1">
                        {(a.tags || []).map((t) => <Chip key={t}>{t}</Chip>)}
                        <Chip tone={a.delivered ? "up" : ""} title="Đã gửi tới kênh nhận (Telegram)">{a.delivered ? "Đã gửi" : "Chưa gửi"}</Chip>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
              <Loadmore shown={d.items.length} pageSize={limit} onMore={() => setLimit(limit + 50)} loading={q.isFetching} />
            </>
          )}
        </Async>
      </div>
    </Panel>
  );
}

/** Đọc `#/canh-bao/new?symbol=EURUSD` -> {symbol} rồi dọn hash (không tạo thêm mục lịch sử). */
function readPrefill() {
  const m = /^#\/?canh-bao\/new(?:\?(.*))?$/.exec(location.hash);
  if (!m) return null;
  const qp = new URLSearchParams(m[1] || "");
  const sym = qp.get("symbol") || "";
  const px = Number(qp.get("price"));
  return { symbol: /^[A-Za-z0-9:._-]{1,32}$/.test(sym) ? sym : "", price: Number.isFinite(px) && px > 0 ? String(px) : "", op: qp.get("op") === "lte" ? "lte" : "gte", n: Date.now() };
}

const TABS = [["rules", "Quy tắc của tôi"], ["events", "Lịch sử kích hoạt"], ["system", "Cảnh báo hệ thống"]];

export default function Alerts() {
  const [tab, setTab] = useState("rules");
  const [prefill, setPrefill] = useState(null);

  useEffect(() => {
    const h = () => {
      const p = readPrefill();
      if (p) { setTab("rules"); setPrefill(p); history.replaceState(null, "", "#/canh-bao"); }
    };
    h();
    addEventListener("hashchange", h);
    return () => removeEventListener("hashchange", h);
  }, []);
  const done = useCallback(() => setPrefill(null), []);

  return (
    <>
      <PageHead title="Cảnh báo" sub="Tạo quy tắc cảnh báo theo giá, chỉ báo, tin tức, tài khoản; xem lịch sử kích hoạt và cảnh báo của hệ thống. Chỉ thông báo, không đặt lệnh." />
      <Tabs.Root value={tab} onValueChange={setTab} className="flex flex-col flex-1 min-h-0 gap-3">
        <Tabs.List className="flex gap-1 overflow-x-auto shrink-0" aria-label="Nhóm cảnh báo">
          <div className="seg">{TABS.map(([v, l]) => <Tabs.Trigger key={v} value={v}>{l}</Tabs.Trigger>)}</div>
        </Tabs.List>
        <Tabs.Content value="rules" className="outline-none"><RulesTab prefill={prefill} onPrefillDone={done} /></Tabs.Content>
        <Tabs.Content value="events" className="outline-none flex flex-col flex-1 min-h-0"><EventsTab /></Tabs.Content>
        <Tabs.Content value="system" className="outline-none flex flex-col flex-1 min-h-0"><SystemAlerts /></Tabs.Content>
      </Tabs.Root>
    </>
  );
}
