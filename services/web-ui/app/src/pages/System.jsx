import { Activity, Database, Radio, ServerCog, TriangleAlert } from "lucide-react";
import { Async, Chip, Freshness, PageHead, Panel, Stat, cn } from "../components/ui";
import { DataSourcesPanels } from "../components/datasources";
import { useAlerts, useNow, useSystem } from "../lib/queries";
import { useStream } from "../lib/stream";
import { clean, dateTime, dur, rel } from "../lib/format";
import { marketClosed } from "../lib/freshness";

const SRC_LABEL = {
  bars: "Nến giá", quotes: "Giá tick", news: "Tin tức", calendar: "Lịch kinh tế", expert_signals: "Tín hiệu chuyên gia",
  expert_positions: "Vị thế chuyên gia", accounts: "Tài khoản MT", alerts: "Cảnh báo",
};
// Ngưỡng "cũ" theo loại dữ liệu (giây). Lịch/vị thế đổi chậm nên cho phép lâu hơn.
const FX_ONLY = new Set(["bars", "quotes"]);
const STALE = { bars: 900, quotes: 300, news: 7200, calendar: 172800, expert_signals: 604800, expert_positions: 1209600, accounts: 300, alerts: 604800 };
const SRC_NOTE = { prometheus: "Trạng thái từng service", redis: "Suy ra từ sự kiện cuối trên bus (chưa cấu hình PROMETHEUS_URL)", none: "Không có nguồn trạng thái" };

function LagChip({ s }) {
  if (s == null) return <Chip>chưa có sự kiện</Chip>;
  return <Chip tone={s < 120 ? "up" : s < 900 ? "accent" : "down"}>{dur(s)}</Chip>;
}

export default function System() {
  const sys = useSystem();
  const errs = useAlerts({ limit: 8, level: "crit" });
  const warns = useAlerts({ limit: 8, level: "warn" });
  const st = useStream();
  const now = useNow(1000);
  const fxClosed = marketClosed("EURUSD", now);
  const recent = [...(errs.data?.items || []), ...(warns.data?.items || [])].sort((a, b) => new Date(b.ts) - new Date(a.ts)).slice(0, 8);

  return (
    <>
      <PageHead title="Hệ thống" sub="Sức khoẻ từng service, độ trễ luồng sự kiện và độ mới của dữ liệu. Làm mới mỗi 10 giây." />
      <div className="sys-grid">
        <Panel title="Service" icon={ServerCog} className="sys-svc" scroll
          right={sys.data && <span className="text-[11.5px] text-faint hidden sm:inline">{SRC_NOTE[sys.data.services_source]}</span>}>
          <Async q={sys} rows={5} empty="Chưa có thông tin service." isEmpty={(d) => !d.services.length}
            hint="Đặt PROMETHEUS_URL=http://prometheus:9090 cho api-gateway để biết service nào ngừng chạy.">
            {(d) => (
              <ul className="m-0 p-0 list-none divide-y divide-line">
                {d.services.map((s) => (
                  <li key={s.name} className="flex items-center gap-3 py-[7px]">
                    <span className="live-dot" style={{ background: s.up ? "var(--up)" : "var(--down)" }} aria-hidden="true" />
                    <b className="flex-1">{s.name}</b>
                    <Chip tone={s.up ? "up" : "down"}>{s.up ? "Hoạt động" : "Ngừng"}</Chip>
                    <span className="text-[11.5px] text-faint w-[84px] text-right" title={dateTime(s.last_scrape)}>{rel(s.last_scrape, now)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Async>
        </Panel>

        <Panel title="Luồng sự kiện (Redis Streams)" icon={Radio} className="sys-str" pad={false} scroll>
          <Async q={sys} rows={6} empty="Chưa đọc được stream.">
            {(d) => (
              <div className="scroll-x">
                <table className="tbl" style={{ minWidth: 480 }}>
                  <thead><tr><th>Stream</th><th className="r">Số sự kiện</th><th>Sự kiện cuối</th><th className="r" title="Thời gian từ sự kiện cuối tới bây giờ">Độ trễ</th></tr></thead>
                  <tbody>
                    {d.streams.map((s) => (
                      <tr key={s.stream}>
                        <td className="font-medium">{s.stream}</td>
                        <td className="r num">{s.length == null ? "—" : s.length.toLocaleString("en-US")}</td>
                        <td className="text-muted whitespace-nowrap">{dateTime(s.last_event_at)}</td>
                        <td className="r"><LagChip s={s.lag_seconds} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Async>
        </Panel>

        <Panel title="Độ mới của dữ liệu" icon={Database} className="sys-src" pad={false} scroll>
          <Async q={sys} rows={6} empty="Chưa có thông tin cập nhật.">
            {(d) => (
              <div className="scroll-x">
                <table className="tbl" style={{ minWidth: 480 }}>
                  <thead><tr><th>Dữ liệu</th><th>Lần cập nhật cuối</th><th className="r">24 giờ qua</th><th>Độ mới</th></tr></thead>
                  <tbody>
                    {d.sources.map((s) => {
                      const stale = s.age_seconds == null || s.age_seconds > (STALE[s.name] ?? 3600);
                      return (
                        <tr key={s.name}>
                          <td className="font-medium">{SRC_LABEL[s.name] || s.name}</td>
                          <td className="text-muted whitespace-nowrap">{dateTime(s.last_ts)}</td>
                          <td className="r num">{s.count_24h.toLocaleString("en-US")}</td>
                          <td><Freshness now={now} ts={s.last_ts} warnAfterS={(STALE[s.name] ?? 3600) / 4} staleAfterS={STALE[s.name] ?? 3600} closed={FX_ONLY.has(s.name) ? fxClosed : false} label={SRC_LABEL[s.name] || s.name} /></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Async>
        </Panel>

                <Panel title="Kết nối của trình duyệt" icon={Activity} className="sys-conn">
          <div className="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-3">
            <Stat label="WebSocket" value={st.status === "open" ? "Đang nối" : st.status === "connecting" ? "Đang nối…" : "Mất"} tone={st.status === "open" ? "up" : "down"} />
            <Stat label="Sự kiện nhận" value={st.count.toLocaleString("en-US")} />
            <Stat label="Tin cuối" value={st.lastMsgAt ? rel(st.lastMsgAt, now) : "—"} />
          </div>
          {sys.data && <div className="mt-3 text-[12px] text-faint">Gateway v{sys.data.version} · {sys.data.ws_connections} kết nối WebSocket · cập nhật {rel(sys.data.generated_at, now)}</div>}
        </Panel>
                <Panel title="Lỗi và cảnh báo gần đây" icon={TriangleAlert} className="sys-err" scroll>
          <Async q={{ isPending: errs.isPending || warns.isPending, isError: errs.isError, error: errs.error, refetch: errs.refetch, data: recent }} rows={3} empty="Không có lỗi hoặc cảnh báo nào gần đây.">
            {(rows) => (
              <ul className="m-0 p-0 list-none divide-y divide-line">
                {rows.map((a) => (
                  <li key={a.id} className="py-[6px] flex gap-2 items-start">
                    <Chip tone={a.level === "crit" ? "down" : "accent"}>{a.level === "crit" ? "Lỗi" : "Cảnh báo"}</Chip>
                    <span className="flex-1 min-w-0"><span className="block truncate" title={clean(a.body || a.title)}>{clean(a.title)}</span><span className="text-[11.5px] text-faint">{dateTime(a.ts)}</span></span>
                  </li>
                ))}
              </ul>
            )}
          </Async>
        </Panel>
      </div>
      <DataSourcesPanels />
    </>
  );
}
