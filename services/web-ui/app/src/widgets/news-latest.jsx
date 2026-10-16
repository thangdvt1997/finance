import { Newspaper } from "lucide-react";
import { Async, Chip } from "../components/ui";
import { useNews } from "../lib/queries";
import { clean, rel, symbolLabel } from "../lib/format";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "news-latest", title: "Tin mới", icon: Newspaper, group: "Tin & lịch", linkable: true, desc: "Tin mới nhất; khi gắn kênh màu sẽ lọc theo mã đang xem.",
  defaultSize: { w: 7, h: 12 }, minSize: { w: 4, h: 4 },
  configSchema: [{ key: "limit", label: "Số tin", type: "number", default: 20, min: 5, max: 60 }, { key: "bySymbol", label: "Lọc theo mã đang theo dõi (khi gắn kênh)", type: "bool", default: true }],
};

export default function NewsLatest() {
  const { config, symbol, channel } = useWidget();
  const follow = !!channel && config.bySymbol !== false && symbol;
  const q = useNews({ symbol: follow ? symbol : undefined, limit: config.limit || 20 });
  return (
    <div className="tm-fill tm-scroll tm-pad">
      {follow && <div className="tm-sub mb-1">Lọc theo {symbolLabel(symbol)}</div>}
      <Async q={q} rows={6} empty="Chưa có tin phù hợp.">
        {(d) => (
          <ul className="m-0 p-0 list-none divide-y divide-line">
            {d.items.map((n) => (
              <li key={n.url} className="py-2">
                <a href={n.url} target="_blank" rel="noopener noreferrer" className="no-underline font-medium leading-snug hover:text-accent text-[12.5px]">{clean(n.title)}</a>
                <div className="flex flex-wrap items-center gap-2 mt-[2px] text-[11.5px] text-faint">
                  <span>{rel(n.published_at)}</span>
                  {n.sentiment != null && <Chip tone={n.sentiment > 0.15 ? "up" : n.sentiment < -0.15 ? "down" : ""}>{n.sentiment > 0 ? "+" : ""}{n.sentiment.toFixed(2)}</Chip>}
                  {(n.symbols || []).slice(0, 3).map((s) => <Chip key={s}>{symbolLabel(s)}</Chip>)}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Async>
    </div>
  );
}
