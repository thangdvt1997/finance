// Trang Cài đặt / Tuỳ chọn: giao diện, màu tăng-giảm, vùng & định dạng, thông báo, dữ liệu cá nhân. Lưu localStorage ngay + user_prefs.ux ở máy chủ.
import { useMemo, useState } from "react";
import { Bell, Cloud, Globe2, Palette, RotateCcw, Trash2, TrendingUp, Volume2, SlidersHorizontal } from "lucide-react";
import { PageHead, Panel, Seg, cn } from "../components/ui";
import { ACCENTS, UPDOWN, effectiveTheme, useSettings } from "../ux/settings";
import { browserTz, tzOffsetLabel, validTz, VN_TZ } from "../ux/fmtconfig";
import { beep, soundReady } from "../ux/sound";
import { CATS, clearNotifs, notify, toast } from "../ux/bus";
import { appCmd } from "../ux/actions";
import { usePrefsState } from "../lib/prefs";
import { dateTime, money, price, time } from "../lib/format";
import { useNow } from "../lib/queries";
import { lset } from "../lib/lstore";


export const meta = { path: "cai-dat", label: "Cài đặt", group: "Tiện ích", icon: SlidersHorizontal, order: 10, roles: ["master", "client"], keywords: "tuy chon giao dien theme mau nhan mat do co chu mui gio am bao thong bao settings preferences" };
const POPULAR = [VN_TZ, "Asia/Bangkok", "Asia/Singapore", "Asia/Hong_Kong", "Asia/Shanghai", "Asia/Tokyo", "Asia/Seoul", "Asia/Dubai", "Australia/Sydney", "Europe/London", "Europe/Paris", "Europe/Berlin", "America/New_York", "America/Chicago", "America/Los_Angeles", "UTC"];

function Row({ label, sub, id, children }) {
  return (
    <div className="ux-row">
      <div><label className="lbl" htmlFor={id}>{label}</label>{sub && <p className="sub">{sub}</p>}</div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
function Switch({ checked, onChange, label, id }) {
  return <button type="button" role="switch" id={id} aria-checked={checked} aria-label={label} className="ux-toggle" onClick={() => onChange(!checked)} />;
}
const ud = (k) => (
  <span className="ux-ud inline-flex items-center gap-3 num text-[13px]" data-k={k}>
    <span className="u">▲ +0,42%</span><span className="d">▼ −0,18%</span>
  </span>
);

export default function Settings() {
  const [s, set, reset] = useSettings();
  const prefs = usePrefsState();
  const now = useNow(1000);
  const [tzq, setTzq] = useState("");
  const [perm, setPerm] = useState(() => (typeof Notification === "undefined" ? "unsupported" : Notification.permission));
  const zones = useMemo(() => {
    let all = [];
    try { all = Intl.supportedValuesOf("timeZone"); } catch { all = POPULAR; }
    const q = tzq.trim().toLowerCase().replace(/ /g, "_");
    return [...new Set([...POPULAR, ...all])].filter((z) => !q || z.toLowerCase().includes(q));
  }, [tzq]);
  const tzSel = s.tz === "vn" ? VN_TZ : s.tz === "auto" ? "__auto" : s.tz;
  const tzVal = s.tz === "vn" ? VN_TZ : s.tz === "auto" ? browserTz() : s.tz;

  async function askPerm() {
    if (typeof Notification === "undefined") return;
    const p = await Notification.requestPermission();
    setPerm(p);
    set({ browserNotif: p === "granted" });
    toast({ tone: p === "granted" ? "ok" : "warn", title: p === "granted" ? "Đã bật thông báo trình duyệt" : "Trình duyệt chưa cho phép thông báo", body: p === "denied" ? "Hãy cho phép thông báo cho trang này trong cài đặt trình duyệt." : undefined, ttl: 4000 });
  }
  const sync = prefs.status === "saving" ? "Đang lưu lên máy chủ…" : prefs.status === "error" || !prefs.available ? "Chưa đồng bộ được lên máy chủ — đang lưu trong trình duyệt này." : prefs.status === "dirty" ? "Sắp lưu lên máy chủ…" : "Đã lưu lên tài khoản của bạn và đồng bộ giữa các thiết bị.";
  const eff = effectiveTheme(s);

  return (
    <>
      <PageHead title="Cài đặt" sub="Tuỳ chỉnh giao diện, định dạng và thông báo. Thay đổi có hiệu lực ngay và được lưu theo tài khoản của bạn." right={<span className="text-[12px] text-muted" role="status" aria-live="polite"><Cloud size={12} className="inline mr-1" aria-hidden="true" />{sync}</span>} />
      <div className="grid gap-3 lg:grid-cols-2 items-start">
        <Panel title="Giao diện" icon={Palette}>
          <div className="ux-sec">
            <Row label="Chế độ sáng/tối" sub={`Đang hiển thị: ${eff === "dark" ? "tối" : "sáng"}. “Tự động” theo cài đặt của thiết bị.`}>
              <Seg label="Chế độ giao diện" value={s.theme} onChange={(v) => set({ theme: v })} options={[{ value: "auto", label: "Tự động" }, { value: "light", label: "Sáng" }, { value: "dark", label: "Tối" }]} />
            </Row>
            <Row label="Màu nhấn" sub="Dùng cho nút, liên kết và mục đang chọn. Đã kiểm tra độ tương phản ở cả hai giao diện.">
              <div className="flex flex-wrap gap-2" role="group" aria-label="Màu nhấn">
                {Object.entries(ACCENTS).map(([k, a]) => (
                  <button key={k} type="button" className="ux-swatch" aria-pressed={s.accent === k} aria-label={a.label} title={a.label} onClick={() => set({ accent: k })} style={{ background: eff === "dark" ? a.dark : a.light }}>
                    {s.accent === k ? "✓" : ""}
                  </button>
                ))}
              </div>
            </Row>
            <Row label="Mật độ" sub="Gọn: nhiều dữ liệu hơn trên một màn hình (phù hợp màn lớn).">
              <Seg label="Mật độ hiển thị" value={s.density} onChange={(v) => set({ density: v })} options={[{ value: "comfortable", label: "Thoải mái" }, { value: "compact", label: "Gọn" }]} />
            </Row>
            <Row label="Cỡ chữ" sub="Phóng to/thu nhỏ toàn bộ giao diện.">
              <Seg label="Cỡ chữ" value={String(s.fontScale)} onChange={(v) => set({ fontScale: +v })} options={[{ value: "90", label: "90%" }, { value: "100", label: "100%" }, { value: "110", label: "110%" }, { value: "125", label: "125%" }]} />
            </Row>
            <Row label="Tương phản" sub="Cao: viền và chữ phụ đậm hơn, liên kết gạch chân.">
              <Seg label="Tương phản" value={s.contrast} onChange={(v) => set({ contrast: v })} options={[{ value: "normal", label: "Bình thường" }, { value: "high", label: "Cao" }]} />
            </Row>
            <Row label="Chuyển động" sub="Giảm: tắt băng giá chạy, nhấp nháy, hiệu ứng chuyển. Mặc định theo thiết bị.">
              <Seg label="Chuyển động" value={s.motion === "full" ? "system" : s.motion} onChange={(v) => set({ motion: v })} options={[{ value: "system", label: "Theo thiết bị" }, { value: "reduce", label: "Giảm" }]} />
            </Row>
          </div>
        </Panel>

        <Panel title="Màu tăng / giảm" icon={TrendingUp}>
          <fieldset className="border-0 p-0 m-0 grid gap-2">
            <legend className="sr-only">Quy ước màu tăng giảm</legend>
            {Object.entries(UPDOWN).map(([k, u]) => (
              <label key={k} className={cn("ux-prev flex items-center gap-3 cursor-pointer flex-wrap", s.updown === k && "!border-[var(--accent)]")}>
                <input type="radio" name="updown" checked={s.updown === k} onChange={() => set({ updown: k })} />
                <span className="min-w-0 flex-1"><b className="block text-[13px]">{u.label}</b><span className="text-[12px] text-muted">{u.sub}</span></span>
                {ud(k)}
              </label>
            ))}
          </fieldset>
          <p className="m-0 mt-2 text-[12px] text-muted">Chế độ xanh dương/cam còn thêm ký hiệu ▲▼ trên huy hiệu để không phụ thuộc màu. Biểu đồ nến đọc lại màu khi bạn đổi (hoặc tải lại trang).</p>
        </Panel>

        <Panel title="Vùng & định dạng" icon={Globe2}>
          <div className="ux-sec">
            <Row label="Múi giờ" sub="Mặc định giờ Việt Nam. Khi khác giờ Việt Nam, thanh trên hiện nhãn múi giờ để tránh nhầm." id="ux-tz">
              <div className="grid gap-2">
                <div className="flex gap-2 flex-wrap">
                  <input className="field flex-1 min-w-[8rem]" type="search" placeholder="Tìm múi giờ (vd: new_york)" aria-label="Lọc múi giờ" value={tzq} onChange={(e) => setTzq(e.target.value)} />
                </div>
                <select id="ux-tz" className="field w-full" value={tzSel} onChange={(e) => { const v = e.target.value; set({ tz: v === VN_TZ ? "vn" : v === "__auto" ? "auto" : v }); }}>
                  <option value="__auto">Theo trình duyệt ({browserTz()})</option>
                  {zones.map((z) => <option key={z} value={z}>{z === VN_TZ ? "Giờ Việt Nam — " : ""}{z.replace(/_/g, " ")} ({tzOffsetLabel(z)})</option>)}
                </select>
                {!validTz(tzVal) && <span className="text-down text-[12px]">Múi giờ không hợp lệ.</span>}
              </div>
            </Row>
            <Row label="Kiểu ngày giờ" sub="Ví dụ hiển thị theo lựa chọn hiện tại:" id="ux-date">
              <div className="grid gap-2">
                <Seg label="Kiểu ngày" value={s.dateFmt} onChange={(v) => set({ dateFmt: v })} options={[{ value: "vi", label: "Việt (dd/mm)" }, { value: "en", label: "Anh (dd/mm/yyyy)" }, { value: "iso", label: "ISO (yyyy-mm-dd)" }]} />
                <span className="num text-[12.5px] text-muted">{dateTime(now)} · {time(now)}</span>
              </div>
            </Row>
            <Row label="Kiểu số" sub="Dấu phân cách hàng nghìn và thập phân:">
              <div className="grid gap-2">
                <Seg label="Kiểu số" value={s.numFmt} onChange={(v) => set({ numFmt: v })} options={[{ value: "en", label: "1,234.56" }, { value: "vi", label: "1.234,56" }]} />
                <span className="num text-[12.5px] text-muted">EURUSD {price("EURUSD", 1.08456)} · XAUUSD {price("XAUUSD", 2412.5)} · {money(12345.6, "USD")}</span>
              </div>
            </Row>
            <Row label="Ký hiệu tiền" sub="Chỉ đổi cách ghi, không quy đổi tỷ giá.">
              <div className="grid gap-2">
                <Seg label="Ký hiệu tiền" value={s.currency} onChange={(v) => set({ currency: v })} options={[{ value: "code", label: "Mã (USD)" }, { value: "symbol", label: "Ký hiệu ($)" }]} />
                <span className="num text-[12.5px] text-muted">{money(12345.6, "USD")} · {money(980.5, "EUR")} · {money(2500000, "VND")}</span>
              </div>
            </Row>
          </div>
        </Panel>

        <Panel title="Thông báo" icon={Bell}>
          <div className="ux-sec">
            <Row label="Toast trong trang" sub="Hộp thông báo nhỏ khi có cảnh báo/tin mới." id="ux-toasts"><Switch id="ux-toasts" label="Bật toast" checked={s.toasts} onChange={(v) => set({ toasts: v })} /></Row>
            <Row label="Âm báo" sub={soundReady() ? "Âm tạo trực tiếp, không tải tệp." : "Trình duyệt chỉ cho phát âm sau khi bạn chạm/bấm vào trang."} id="ux-sound">
              <div className="flex items-center gap-3 flex-wrap">
                <Switch id="ux-sound" label="Bật âm báo" checked={s.sound} onChange={(v) => { set({ sound: v }); if (v) beep("info", s.soundVol); }} />
                <label className="flex items-center gap-2 text-[12.5px]"><Volume2 size={14} aria-hidden="true" /><span className="sr-only">Âm lượng</span>
                  <input type="range" min="0" max="1" step="0.05" value={s.soundVol} onChange={(e) => set({ soundVol: +e.target.value })} aria-label="Âm lượng âm báo" />
                </label>
                <button type="button" className="btn" onClick={() => { if (!beep("warn", s.soundVol)) toast({ tone: "warn", title: "Chưa phát được âm", body: "Chạm vào trang một lần rồi thử lại.", ttl: 3500 }); }}>Nghe thử</button>
              </div>
            </Row>
            <Row label="Thông báo trình duyệt" sub="Hiện khi tab đang ẩn. Cần cấp quyền." id="ux-bn">
              <div className="flex items-center gap-3 flex-wrap">
                {perm === "unsupported" ? <span className="text-muted text-[12.5px]">Trình duyệt này không hỗ trợ.</span> : perm === "granted" ? <Switch id="ux-bn" label="Bật thông báo trình duyệt" checked={s.browserNotif} onChange={(v) => set({ browserNotif: v })} />
                  : <button type="button" className="btn" onClick={askPerm} disabled={perm === "denied"}>{perm === "denied" ? "Đã bị chặn trong trình duyệt" : "Cho phép thông báo"}</button>}
              </div>
            </Row>
            <Row label="Loại thông báo" sub="Tắt loại nào thì không toast/âm/đẩy cho loại đó (vẫn lưu trong chuông).">
              <div className="grid gap-1">
                {Object.entries(CATS).map(([k, l]) => (
                  <label key={k} className="flex items-center gap-2 text-[13px] cursor-pointer min-h-[28px]"><input type="checkbox" checked={s.notifCats[k] !== false} onChange={(e) => set({ notifCats: { ...s.notifCats, [k]: e.target.checked } })} /> {l}</label>
                ))}
              </div>
            </Row>
            <Row label="Thử ngay" sub="Gửi một thông báo mẫu qua các kênh đang bật.">
              <button type="button" className="btn" onClick={() => notify({ key: `test:${Date.now()}`, cat: "alert", sev: "warn", title: "Thông báo thử", body: "Nếu thấy hộp này, toast hoạt động. Đã ghi vào chuông thông báo.", href: "#/cai-dat" })}>Gửi thông báo thử</button>
            </Row>
          </div>
        </Panel>

        <Panel title="Dữ liệu cá nhân" icon={RotateCcw} className="lg:col-span-2">
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn" onClick={() => appCmd("tour")}>Xem lại hướng dẫn làm quen</button>
            <button type="button" className="btn" onClick={() => { if (confirm("Đặt lại mọi cài đặt giao diện về mặc định?")) { reset(); toast({ tone: "ok", title: "Đã đặt lại cài đặt", ttl: 2500 }); } }}><RotateCcw size={13} aria-hidden="true" /> Đặt lại cài đặt</button>
            <button type="button" className="btn" onClick={() => { if (confirm("Xoá toàn bộ thông báo trên thiết bị này?")) { clearNotifs(); toast({ tone: "ok", title: "Đã xoá thông báo", ttl: 2000 }); } }}><Trash2 size={13} aria-hidden="true" /> Xoá thông báo</button>
            <button type="button" className="btn" onClick={() => { if (confirm("Xoá lịch sử trang gần đây và các trang đã đánh dấu trên thiết bị này?")) { lset("ts-recent", []); lset("ts-bookmarks", []); location.reload(); } }}><Trash2 size={13} aria-hidden="true" /> Xoá lịch sử &amp; đánh dấu</button>
          </div>
          <p className="m-0 mt-3 text-[12px] text-muted max-w-[80ch]">Cài đặt giao diện lưu trong tuỳ chọn tài khoản trên máy chủ (đồng bộ nhiều thiết bị) và dự phòng trong trình duyệt. Thông báo, lịch sử trang gần đây và trang đã đánh dấu chỉ lưu trên thiết bị này. Không thu thập thông tin định danh hay dữ liệu theo dõi hành vi.</p>
          <p className="m-0 mt-1 text-[12px] text-faint">Thay đổi gần nhất: {s.t ? dateTime(s.t) : "chưa có"}.</p>
        </Panel>
      </div>
    </>
  );
}
