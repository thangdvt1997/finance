import { Activity } from "lucide-react";
import { Async, Chip } from "../components/ui";
import { useSystem, useNow } from "../lib/queries";
import { useStream } from "../lib/stream";
import { rel } from "../lib/format";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "system-status", title: "Trạng thái hệ thống", icon: Activity, group: "Hệ thống", desc: "Số service hoạt động, kết nối thời gian thực, service ngừng.",
  defaultSize: { w: 6, h: 8 }, minSize: { w: 4, h: 4 },
  configSchema: [{ key: "all", label: "Liệt kê cả service đang chạy tốt", type: "bool", default: false }],
};

export default function SystemStatus() {
  const { config } = useWidget();
  const sys = useSystem();
  const st = useStream();
  const now = useNow(2000);
  const on = st.status === "open";
  return (
    <div className="tm-fill tm-pad gap-2 overflow-auto">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={on ? "up" : "down"}><span className="live-dot" style={on ? undefined : { background: "var(--down)" }} aria-hidden="true" />{on ? "Luồng giá trực tiếp" : st.status === "connecting" ? "Đang nối…" : "Mất kết nối"}</Chip>
        {st.lastMsgAt ? <span className="tm-sub">tin gần nhất {rel(st.lastMsgAt, now)}</span> : null}
      </div>
      <Async q={sys} rows={3} empty="Chưa có trạng thái service." isEmpty={(d) => !d.services.length}>
        {(d) => {
          const down = d.services.filter((s) => !s.up);
          const upN = d.services.length - down.length;
          return (
            <>
              <div className="flex items-baseline gap-2"><span className="num text-[22px]" style={{ color: down.length ? "var(--down)" : "var(--up)" }}>{upN}/{d.services.length}</span><span className="text-muted text-[12.5px]">service hoạt động</span></div>
              <div className="flex flex-wrap gap-[5px]">
                {(config.all ? d.services : down).map((s) => <Chip key={s.name} tone={s.up ? "up" : "down"}>{s.name}<span className="sr-only">{s.up ? " hoạt động" : " ngừng"}</span></Chip>)}
                {!config.all && !down.length && <span className="text-up text-[12.5px]">Tất cả service đang chạy tốt.</span>}
              </div>
            </>
          );
        }}
      </Async>
      <a href="#/he-thong" className="tm-sub mt-auto">Chi tiết hệ thống →</a>
    </div>
  );
}
