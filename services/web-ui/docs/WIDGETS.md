# Terminal — khung widget & trang tự đăng ký

> Mục tiêu: agent khác chỉ cần **thả 1 file** vào `app/src/widgets/` (widget) hoặc `app/src/pages/` (trang). Không sửa `App.jsx`.
> Không build/chạy local: sửa file rồi `D:\Work\trading-system\deploy.sh "up -d --build web-ui"` (xem README).

## 1. Widget: `app/src/widgets/<tên>.jsx`

```jsx
import { LineChart } from "lucide-react";
import { useWidget } from "../terminal/ui";

export const meta = {
  id: "my-chart",                 // duy nhất, kebab-case
  title: "Biểu đồ",               // tiêu đề mặc định + tên trong danh mục
  icon: LineChart,                // icon: BẮT BUỘC import từ "lucide-react"
  group: "Biểu đồ",               // nhóm trong danh mục "Thêm widget"
  desc: "Mô tả một dòng.",
  defaultSize: { w: 10, h: 12 },  // đơn vị lưới: 24 cột; 1 hàng ≈ 36px (28px + khoảng cách 8px)
  minSize: { w: 5, h: 6 },
  linkable: true,                 // true = widget theo dõi 1 mã, có thể gắn kênh màu (đổi mã đồng bộ giữa các widget cùng màu)
  configSchema: [                 // form cấu hình tự dựng (menu ⋯ → Cấu hình…)
    { key: "tf", label: "Khung thời gian", type: "select", default: "H1", options: ["M5", "M15", "H1", "H4", "D1"] },
  ],
};

export default function MyChart() {
  const { symbol, setSymbol, config, setConfig, size, channel } = useWidget(); // cũng được truyền qua props với cùng tên
  return <div className="tm-fill">…</div>;
}
```

**Quy tắc `meta`** — plugin build `app/vite-plugin-ts-meta.js` đọc nó bằng phân tích văn bản (không chạy mã) để thanh điều hướng/danh mục có metadata đồng bộ mà không kéo cả widget vào bundle chính (widget vẫn tải lười khi hiển thị):
chỉ literal thuần (chuỗi/số/bool/mảng/đối tượng); `icon` là tên import từ `lucide-react`; không template `${}`, không hàm, không biến khác. Thiếu `meta` → widget bị bỏ qua (cảnh báo console).

**Props / `useWidget()`**

| trường | ý nghĩa |
|---|---|
| `id`, `type`, `wsId` | id thể hiện, `meta.id`, id workspace |
| `config` | cấu hình đã gộp: mặc định trong `configSchema` + giá trị người dùng chỉnh |
| `setConfig(patch)` | gộp `patch` vào cấu hình (`undefined` = xoá khoá). Tự lưu (localStorage ngay + máy chủ sau ~0,8s) |
| `symbol`, `setSymbol(s)` | chỉ khi `linkable`. `symbol` = mã của kênh màu (nếu gắn kênh) hoặc `config.symbol`. `setSymbol` cập nhật cả kênh → mọi widget cùng màu đổi theo |
| `channel` | `null` hoặc `red/orange/yellow/green/cyan/blue/purple` |
| `size` | `{w,h}` pixel của thân widget (ResizeObserver) — dùng để vẽ biểu đồ đúng cỡ |
| `locked`, `maximized`, `kiosk` | bố cục đang khoá / đang phóng to / chế độ trình chiếu |

**Dựng thân widget**: thân (`.tm-wb`) cao đúng ô lưới, `overflow:auto`. Tiện ích CSS: `tm-fill` (cột flex đầy ô), `tm-scroll` (vùng cuộn trong `tm-fill`), `tm-pad` (đệm), `tm-tbl` (bảng dày, hàng chọn được qua `aria-selected`), `tm-sub` (chữ phụ). Biến màu `--up --down --accent --muted --faint --line --panel…`; class `num`, `up`, `down`, `chip`, `btn`, `field`, `seg`. Dữ liệu qua `lib/queries.js`, `lib/stream.js` (`useQuote`), `lib/format.js`. Văn bản từ máy chủ đi qua `clean()`/`scrub()` — **KHÔNG hiển thị tên nguồn dữ liệu** (docs/UI_NO_SOURCES.md; kiểm bằng `scripts/lint-sources.cjs`).
Dùng chung từ `terminal/ui.jsx`: `useWidget`, `SymbolInput` (ô chọn mã có gợi ý), `Popover`, `MenuList`, `ChannelDot`.

**`configSchema[].type`**: `symbol`, `symbols` (mảng mã), `text`, `textarea`, `number` (`min/max/step`), `select` (`options`: chuỗi hoặc `{value,label}`), `bool`, `multi` (mảng giá trị từ `options`). Trường chung: `key`, `label`, `default`, `help`.

**Khung tự có** (không cần code): tiêu đề (kéo để di chuyển, nhấp đúp = phóng to), nút kênh màu (khi `linkable`), menu ⋯ (Cấu hình, Phóng to, Nhân bản, Xuất ảnh PNG, Cỡ nhỏ/vừa/lớn, Xoá), kéo góc dưới-phải để đổi cỡ, biên lỗi + Suspense.

**Lưu trữ**: mỗi workspace = `{n:tên, l:khoá, x:[{i,t,x,y,w,h,c?,k?,n?}], c:{kênh→mã}}` trong `prefs.tm` (máy chủ `/v1/user/prefs`, **tổng giới hạn 16KB** dùng chung với nhóm theo dõi → `config` phải NHỎ) và mirror `localStorage["ts-tm1"]`. Quá ngưỡng ~11KB: tự chuyển sang chỉ lưu cục bộ và báo trên thanh công cụ.

**Tuỳ chọn khung**: `meta.bare: true` = ẩn tiêu đề, chỉ hiện khi rê chuột/focus (dùng cho băng giá chạy ngang). Toàn màn hình/trình chiếu (`Esc` thoát) co chiều cao hàng để bố cục vừa khít màn hình và có thể tự xoay workspace; widget nên dựa vào `size` thay vì chiều cao cố định.
**Phím tắt/lệnh**: `Alt+1..9` đổi workspace; `g` rồi `t` mở Terminal; Ctrl-K gõ tên workspace hoặc widget để mở/thêm (đăng ký qua `registerCommandProvider`, xem `terminal/commands.js`). Xoá widget/workspace và đặt lại theo mẫu đều có "Hoàn tác" (toast).
**Máy chủ**: `prefs.tm` đi qua alert-rules `Prefs` (`models.py`, `_clean_tm`): server chỉ giữ cấu trúc đã biết (≤12 workspace × 40 widget, `c` mỗi widget ≤2KB) và LOẠI mọi khoá lạ ở cấp prefs — muốn lưu khoá prefs mới phải thêm vào model đó (kèm test). `user_prefs` dùng chung cho mọi master.
**Workspace mẫu** (`terminal/defaults.js`) tham chiếu widget theo `meta.id`, lấy phương án đầu tiên đang tồn tại: `chart` (→ `quote-card`), `heatmap` (→ `heat-strip`), `news` (→ `news-latest`), `calendar-upcoming`, `watchlist`, `ticker-tape`, `clocks`, `notes`, `account-mini`, `alerts-recent`, `system-status`. Đặt `meta.id` đúng `chart` / `heatmap` / `news` để được tự xếp vào workspace mặc định thay cho bản dự phòng (người dùng đã lưu workspace thì giữ nguyên, có thể thêm tay từ danh mục).

## 2. Trang: `app/src/pages/<Tên>.jsx`

```jsx
import { Wallet } from "lucide-react";
export const meta = { path: "tai-khoan-cua-toi", label: "Tài khoản của tôi", group: "Tài khoản", icon: Wallet,
  roles: ["client"], order: 10, short: "Tài khoản", primary: false, keywords: "equity margin" };
export default function Page({ arg }) { /* arg = phần sau "/" của hash, vd #/path/arg */ }
```

- `roles`: mặc định `["master"]`; giao diện client dùng `["client"]` (hoặc cả hai). Vai trò lấy từ `/auth/me` (`fetchMe` trong `lib/clientsApi.js`); sidebar, thanh dưới (mobile), Ctrl-K và chuyển hướng đều lọc theo vai trò.
- `roles`: ngoài `master`/`client` còn có vai trò phụ `support`, `analyst`, `auditor` (đăng nhập cùng console). `perm` (tuỳ chọn, ví dụ `"fleet.read"`, `"incident.read"`, `"compliance.read"`, `"report.read"`, `"audit.read"`): vai trò phụ chỉ thấy trang khi `perms` của `/auth/me` có quyền đó (master luôn thấy). Chỉ ẩn menu cho gọn — máy chủ vẫn kiểm quyền thật; trang tự kiểm `usePerm()` (lib/fleetQueries.js) để ẩn/khoá nút ghi kèm lý do.
- `group`: nhóm sidebar theo thứ tự `Terminal`, `Thị trường`, `Thông tin`, `Tài khoản`, `Quản trị đội`, `Vận hành`; nhóm mới tự thêm vào cuối. `order` sắp trong nhóm. `primary: true` = hiện trên thanh dưới điện thoại (tối đa 4 trang đầu).
- Trang có sẵn trước đây khai báo ở `shell/legacyPages.js` (giữ nguyên, không cần sửa). Tệp trong `pages/` không có `meta` và không thuộc legacy (vd `PaperQuality.jsx`) là module phụ, không thành trang.
- Cùng ràng buộc literal như widget (đọc bằng plugin).

## 3. Thư viện OSS

`react-grid-layout` 2.x (MIT) — lưới kéo thả/đổi cỡ; `html-to-image` (MIT) — xuất ảnh widget. Ghi công trong `THIRD_PARTY.md`.

## 4. Widget "track record chuyên gia" (2026-10-12)

Dữ liệu từ gateway `/v1/experts/*` (hợp đồng: `services/track-record/CONTRACT.md`); hook trong `lib/trackrecord.js`; thành phần dùng chung trong `components/experts/*` (bảng xếp hạng, hồ sơ chuyên gia dạng drawer, bản đồ đồng thuận, dòng quan điểm, hộp "Phương pháp"). Trang Chuyên gia có tab đầu "Xếp hạng & track record".

| Widget | `meta.id` | Cấu hình | Ghi chú |
|---|---|---|---|
| `widgets/consensus-map.jsx` | `consensus-map` | cửa sổ ngày, tài sản, mức (đồng thuận/nghiêng nhẹ), tối thiểu chuyên gia, số mã, lọc theo mã khi gắn kênh màu | thanh tỷ trọng giảm (đỏ, trái) / tăng (xanh, phải) theo trọng số; bấm hàng để xem ai |
| `widgets/expert-feed.jsx` | `expert-feed` | hướng, mã cố định, số quan điểm, lọc theo mã khi gắn kênh màu | dòng thời gian quan điểm mới; nhãn "Đủ mẫu / Chưa đủ mẫu" |

Quy tắc: không bao giờ vẽ thứ hạng/huy hiệu cho nhóm chưa đủ mẫu; huy hiệu "Vượt ngẫu nhiên (q<0,10)" CHỈ khi `beats_baseline`; nhãn miễn trừ cố định luôn hiện; không render `source`/`url`.
Dữ liệu mẫu khi backend chưa chạy: thêm `?mockexp=1` vào URL (sessionStorage; `?mockexp=0` tắt) — `lib/trackrecordFixture.js`. QA: `qa/run_expert.sh experts.mjs` (MOCK=0 gọi API thật) và `experts_client.mjs` (client-ui) trên VPS.
client-ui: trang `/chuyen-gia` (`pages/Experts.jsx`, bản gọn: top theo điểm + đồng thuận + nhãn miễn trừ); nginx client whitelist `/c/api/v1/experts/...`.
