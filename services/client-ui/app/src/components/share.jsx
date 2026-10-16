// Chia sẻ ảnh báo cáo nhanh: vẽ thẻ PNG bằng Canvas 2D (không thư viện ngoài, dữ liệu không rời máy). Mặc định ẨN số tiền, chỉ hiện %.
import { useEffect, useMemo, useRef, useState } from "react";
import { Download, Share2 } from "lucide-react";
import { Sheet } from "./ui";
import { useActiveAccount } from "../lib/account";
import { useEquity, useJnSummary } from "../lib/queries";
import { accountTitle } from "../lib/auth";
import { dateY, f0, f1, money, vnDayKey, vnDayStart } from "../lib/format";
import { t } from "../lib/i18n";

const W = 1080, H = 1350;

function draw(cv, d) {
  const c = cv.getContext("2d");
  const bg = "#0b1017", fg = "#e6edf6", mu = "#8fa0b6", up = "#2bd08f", dn = "#ff5c7a", ac = "#f0b84f";
  c.fillStyle = bg; c.fillRect(0, 0, W, H);
  const g = c.createRadialGradient(W / 2, 0, 0, W / 2, 0, 900); g.addColorStop(0, "rgba(240,184,79,.18)"); g.addColorStop(1, "rgba(240,184,79,0)"); c.fillStyle = g; c.fillRect(0, 0, W, 700);
  c.textBaseline = "alphabetic";
  const tx = (s, x, y, size, col, weight = 600, align = "left", mono = false) => { c.font = `${weight} ${size}px ${mono ? "JetBrains Mono, monospace" : "Inter Variable, Inter, system-ui, sans-serif"}`; c.fillStyle = col; c.textAlign = align; c.fillText(s, x, y); };
  tx(t("Báo cáo tài khoản"), 72, 110, 40, ac, 700);
  tx(d.title, 72, 170, 54, fg, 700);
  tx(d.sub, 72, 216, 28, mu, 500);
  // thẻ chỉ số
  const card = (x, y, w, h, label, val, col = fg, sub) => {
    c.fillStyle = "#111925"; c.strokeStyle = "#223044"; c.lineWidth = 2; c.beginPath(); c.roundRect(x, y, w, h, 24); c.fill(); c.stroke();
    tx(label, x + 28, y + 50, 26, mu, 500); tx(val, x + 28, y + 112, 52, col, 700, "left", true); if (sub) tx(sub, x + 28, y + h - 26, 24, mu, 500);
  };
  const sg = (v) => (v > 0 ? up : v < 0 ? dn : fg);
  card(72, 270, 454, 170, t("Thay đổi vốn trong kỳ"), d.chg, sg(d.chgV), d.range);
  card(554, 270, 454, 170, t("Mức margin"), d.margin, d.marginCol);
  card(72, 464, 454, 170, t("Tỷ lệ thắng"), d.win, fg, d.n);
  card(554, 464, 454, 170, "Profit factor", d.pf, fg, d.exp);
  // đường vốn
  const x0 = 72, y0 = 690, w = 936, h = 420;
  c.fillStyle = "#111925"; c.strokeStyle = "#223044"; c.beginPath(); c.roundRect(x0, y0, w, h, 24); c.fill(); c.stroke();
  tx(t("Đường vốn"), x0 + 28, y0 + 52, 26, mu, 500);
  const pts = d.series;
  if (pts.length > 1) {
    const lo = Math.min(...pts), hi = Math.max(...pts), span = hi - lo || 1, px = x0 + 40, pw = w - 80, py = y0 + 90, ph = h - 140;
    c.beginPath(); pts.forEach((v, i) => { const X = px + (i / (pts.length - 1)) * pw, Y = py + ph - ((v - lo) / span) * ph; i ? c.lineTo(X, Y) : c.moveTo(X, Y); });
    c.strokeStyle = pts[pts.length - 1] >= pts[0] ? up : dn; c.lineWidth = 4; c.lineJoin = "round"; c.stroke();
    c.lineTo(px + pw, py + ph); c.lineTo(px, py + ph); c.closePath(); c.fillStyle = pts[pts.length - 1] >= pts[0] ? "rgba(43,208,143,.12)" : "rgba(255,92,122,.12)"; c.fill();
  } else tx(t("Chưa đủ dữ liệu"), x0 + w / 2, y0 + h / 2, 30, mu, 500, "center");
  if (d.money) tx(d.money, x0 + w - 28, y0 + 52, 28, fg, 600, "right", true);
  tx(t("Tạo ngày {date}. Số liệu tham khảo, không phải khuyến nghị đầu tư. Ứng dụng chỉ theo dõi, không đặt lệnh.", { date: d.date }), W / 2, 1250, 22, mu, 500, "center");
  tx(d.hide ? t("Số tiền đã được ẩn") : t("Có hiển thị số tiền: cân nhắc trước khi gửi cho người khác"), W / 2, 1290, 22, d.hide ? up : ac, 600, "center");
}

export default function ShareButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="btn sm" onClick={() => setOpen(true)} aria-haspopup="dialog"><Share2 size={16} aria-hidden="true" /> {t("Chia sẻ")}</button>
      {open && <ShareSheet onClose={() => setOpen(false)} />}
    </>
  );
}

function ShareSheet({ onClose }) {
  const { acc, view } = useActiveAccount();
  const [hide, setHide] = useState(true);
  const ref = useRef(null);
  const from = useMemo(() => new Date(Date.now() - 7 * 86400e3).toISOString().slice(0, 16) + ":00Z", []);
  const eq = useEquity(acc?.id, from);
  const jn = useJnSummary(acc?.id, { from: vnDayKey(vnDayStart(-29)), to: vnDayKey(new Date()) });
  const data = useMemo(() => {
    const pts = (eq.data || []).filter((p) => p.equity != null);
    const step = Math.max(1, Math.floor(pts.length / 120));
    const series = pts.filter((_, i) => i % step === 0 || i === pts.length - 1).map((p) => p.equity);
    const first = pts[0]?.equity, last = view?.equity ?? pts[pts.length - 1]?.equity;
    const chgV = first && last != null ? last - first : 0, s = jn.data?.summary;
    const lv = view?.level;
    return {
      title: acc ? accountTitle(acc) : "", sub: acc?.label || acc?.server || t("Tài khoản MT"), hide,
      chg: first ? `${chgV >= 0 ? "+" : ""}${f1((chgV / first) * 100, 2)}%${hide ? "" : ` (${chgV >= 0 ? "+" : ""}${money(chgV)})`}` : "—", chgV, range: t("7 ngày gần nhất"),
      margin: lv == null ? "—" : `${f0(lv)}%`, marginCol: lv == null ? "#e6edf6" : lv < 150 ? "#ff5c7a" : lv < 300 ? "#f0b84f" : "#2bd08f",
      win: s?.win_rate != null ? `${f1(s.win_rate * 100, 1)}%` : "—", n: s?.n ? t("{n} lệnh trong 30 ngày", { n: s.n }) : t("chưa có lệnh đã đóng"),
      pf: s?.profit_factor != null ? f1(s.profit_factor, 2) : "—", exp: s?.expectancy != null ? (hide ? t("kỳ vọng dương/âm theo lệnh") : t("kỳ vọng {v}/lệnh", { v: money(s.expectancy) })) : "",
      series, money: hide ? "" : money(last), date: dateY(new Date()),
    };
  }, [eq.data, jn.data, view, acc, hide]);
  useEffect(() => { if (ref.current) draw(ref.current, data); }, [data]);
  const blob = () => new Promise((r) => ref.current.toBlob(r, "image/png"));
  const share = async () => {
    const b = await blob(); if (!b) return;
    const file = new File([b], "bao-cao-tai-khoan.png", { type: "image/png" });
    try { if (navigator.canShare?.({ files: [file] })) { await navigator.share({ files: [file], title: t("Báo cáo tài khoản") }); return; } } catch { return; }
    save(b);
  };
  const save = (b) => { const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(b), download: "bao-cao-tai-khoan.png" }); a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 3000); };
  return (
    <Sheet title={t("Chia sẻ ảnh báo cáo")} onClose={onClose}>
      <div className="grid gap-3">
        <canvas ref={ref} width={W} height={H} className="w-full rounded-xl border border-line" style={{ aspectRatio: `${W}/${H}`, maxHeight: "46dvh", objectFit: "contain" }} role="img" aria-label={t("Xem trước ảnh báo cáo")} />
        <label className="flex items-center gap-3 min-h-[44px] cursor-pointer"><input type="checkbox" checked={hide} onChange={(e) => setHide(e.target.checked)} /> <span className="text-[14px]">{t("Ẩn số tiền (chỉ hiện phần trăm)")}</span></label>
        <div className="flex gap-2">
          <button className="btn primary" onClick={share}><Share2 size={16} aria-hidden="true" /> {typeof navigator.canShare === "function" ? t("Chia sẻ") : t("Lưu ảnh")}</button>
          <button className="btn" onClick={async () => { const b = await blob(); if (b) save(b); }}><Download size={16} aria-hidden="true" /> {t("Tải ảnh PNG")}</button>
        </div>
        <p className="m-0 text-[12px] text-faint">{t("Ảnh được tạo ngay trên thiết bị của bạn, không tải lên máy chủ. Số tài khoản có hiện trên ảnh.")}</p>
      </div>
    </Sheet>
  );
}
