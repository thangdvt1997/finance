import { Clock3 } from "lucide-react";
import { useNow } from "../lib/queries";
import { cn } from "../components/ui";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "clocks", title: "Phiên & giờ thế giới", icon: Clock3, group: "Công cụ", desc: "Đồng hồ nhiều múi giờ và biểu đồ 24 giờ các phiên Tokyo / London / New York / Hà Nội.",
  defaultSize: { w: 6, h: 9 }, minSize: { w: 4, h: 5 },
  configSchema: [
    { key: "zones", label: "Múi giờ (múi đầu tiên là đồng hồ lớn)", type: "multi", default: ["Asia/Ho_Chi_Minh", "Asia/Tokyo", "Europe/London", "America/New_York"], options: [{ value: "Asia/Ho_Chi_Minh", label: "Hà Nội" }, { value: "Asia/Singapore", label: "Singapore" }, { value: "Asia/Hong_Kong", label: "Hồng Kông" }, { value: "Asia/Tokyo", label: "Tokyo" }, { value: "Australia/Sydney", label: "Sydney" }, { value: "Europe/Frankfurt", label: "Frankfurt" }, { value: "Europe/London", label: "London" }, { value: "America/New_York", label: "New York" }, { value: "America/Chicago", label: "Chicago" }, { value: "UTC", label: "UTC" }] },
    { key: "bar", label: "Hiện biểu đồ phiên 24 giờ", type: "bool", default: true },
  ],
};

const NAME = { "Asia/Ho_Chi_Minh": "Hà Nội", "Asia/Singapore": "Singapore", "Asia/Hong_Kong": "Hồng Kông", "Asia/Tokyo": "Tokyo", "Australia/Sydney": "Sydney", "Europe/Frankfurt": "Frankfurt", "Europe/London": "London", "America/New_York": "New York", "America/Chicago": "Chicago", UTC: "UTC" };
// phiên giao dịch: giờ mở/đóng theo giờ địa phương của sàn (tham khảo, không tính ngày lễ)
const SESS = [
  { id: "tokyo", name: "Tokyo", tz: "Asia/Tokyo", o: 9, c: 15, col: "var(--info)" },
  { id: "london", name: "London", tz: "Europe/London", o: 8, c: 16.5, col: "var(--accent)" },
  { id: "ny", name: "New York", tz: "America/New_York", o: 9.5, c: 16, col: "var(--up)" },
  { id: "hanoi", name: "Hà Nội", tz: "Asia/Ho_Chi_Minh", o: 9, c: 15, col: "var(--down)" },
];
const parts = (tz, d) => Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour12: false, weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }).formatToParts(d).map((x) => [x.type, x.value]));
const offsetH = (tz, d) => {
  const p = parts(tz, d);
  const loc = Date.UTC(2000, 0, 1, Number(p.hour) % 24, Number(p.minute));
  const utc = Date.UTC(2000, 0, 1, d.getUTCHours(), d.getUTCMinutes());
  let o = (loc - utc) / 36e5;
  if (o > 12) o -= 24;
  if (o < -12) o += 24;
  return o;
};

function SessionBar({ d }) {
  const utcH = d.getUTCHours() + d.getUTCMinutes() / 60;
  const W = 240, H = 12, rowH = 17;
  return (
    <svg viewBox={`0 0 ${W} ${SESS.length * rowH + 14}`} className="w-full shrink-0" role="img" aria-label="Các phiên giao dịch trong 24 giờ UTC">
      {[0, 6, 12, 18, 24].map((h) => (
        <g key={h}>
          <line x1={(h / 24) * W} x2={(h / 24) * W} y1="0" y2={SESS.length * rowH} stroke="var(--line)" />
          <text x={(h / 24) * W + (h === 24 ? -2 : 2)} y={SESS.length * rowH + 10} fontSize="8" fill="var(--faint)" textAnchor={h === 24 ? "end" : "start"}>{String(h % 24).padStart(2, "0")}h</text>
        </g>
      ))}
      {SESS.map((s, i) => {
        const off = offsetH(s.tz, d);
        const a = (((s.o - off) % 24) + 24) % 24, b = a + (s.c - s.o);
        const seg = (x1, x2, k) => <rect key={k} x={(x1 / 24) * W} y={i * rowH + 3} width={((x2 - x1) / 24) * W} height={H} rx="3" fill={s.col} opacity=".78" />;
        return (
          <g key={s.id}>
            {b > 24 ? [seg(a, 24, "a"), seg(0, b - 24, "b")] : seg(a, b, "a")}
            <text x="4" y={i * rowH + 12.5} fontSize="8.5" fill="var(--bg)" fontWeight="650">{s.name}</text>
          </g>
        );
      })}
      <line x1={(utcH / 24) * W} x2={(utcH / 24) * W} y1="0" y2={SESS.length * rowH} stroke="var(--fg)" strokeWidth="1.5" />
    </svg>
  );
}

export default function Clocks() {
  const { config, size } = useWidget();
  const now = useNow(1000);
  const d = new Date(now);
  const zones = config.zones?.length ? config.zones : ["Asia/Ho_Chi_Minh"];
  const open = (s) => {
    const p = parts(s.tz, d);
    const h = (Number(p.hour) % 24) + Number(p.minute) / 60;
    const we = p.weekday === "Sat" || p.weekday === "Sun";
    return !we && h >= s.o && h < s.c && !(s.id === "hanoi" && h >= 11.5 && h < 13);
  };
  const main = parts(zones[0], d);
  return (
    <div className="tm-fill tm-pad gap-2 overflow-auto">
      <div className="shrink-0">
        <div className="num leading-none" style={{ fontSize: Math.max(22, Math.min(44, size.w / 6)) }}>{main.hour}:{main.minute}<span className="text-muted" style={{ fontSize: "0.5em" }}>:{main.second}</span></div>
        <div className="tm-sub mt-1">{NAME[zones[0]] || zones[0]} · {main.weekday} {main.day}/{main.month}</div>
      </div>
      <ul className="m-0 p-0 list-none grid gap-[3px] shrink-0">
        {zones.slice(1).map((z) => {
          const p = parts(z, d);
          return <li key={z} className="flex items-center gap-2 text-[12.5px]"><span className="text-muted flex-1 truncate">{NAME[z] || z}</span><span className="tm-sub">{p.weekday} {p.day}/{p.month}</span><span className="num">{p.hour}:{p.minute}:{p.second}</span></li>;
        })}
      </ul>
      <ul className="m-0 p-0 list-none flex flex-wrap gap-x-3 gap-y-1 text-[11.5px]" aria-label="Trạng thái các phiên">
        {SESS.map((s) => {
          const o = open(s);
          return <li key={s.id} className="flex items-center gap-1.5"><span className={cn("live-dot", o && "on")} aria-hidden="true" /><span className={o ? "text-fg" : "text-muted"}>{s.name}</span><span className="sr-only">{o ? "đang mở" : "đóng"}</span></li>;
        })}
      </ul>
      {config.bar !== false && <SessionBar d={d} />}
    </div>
  );
}
