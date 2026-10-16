# Thành phần bên thứ ba

Chỉ dùng thành phần giấy phép MIT/Apache-2.0/ISC/OFL (cho phép dùng thương mại và sửa đổi). Phiên bản cố định trong `app/package-lock.json`; bản build đóng gói sẵn, **không tải gì từ CDN lúc chạy**.

| Thành phần | Dùng để | Giấy phép |
|---|---|---|
| [lightweight-charts](https://github.com/tradingview/lightweight-charts) 5.x (TradingView) | biểu đồ nến + volume. Logo TradingView trên biểu đồ giữ nguyên theo yêu cầu attribution của Apache-2.0 | Apache-2.0 |
| [indicatorts](https://github.com/cinar/indicatorts) 2.2.2 | tính chỉ báo (SMA/EMA, RSI, MACD, Stochastic, ATR, CCI, OBV, PSAR, Ichimoku, Keltner, Donchian, Williams %R) cho biểu đồ Thị trường; phần còn lại (WMA, ADX, Supertrend, Bollinger theo hệ số, VWAP ngày, Pivot, Heikin-Ashi) là công thức chuẩn tự viết ngắn trong `components/chart/indicators.js` | MIT |
| [Apache ECharts](https://github.com/apache/echarts) 6.x | biểu đồ equity (import theo module, tree-shake) | Apache-2.0 |
| [React](https://github.com/facebook/react) 19 | UI | MIT |
| [TanStack Query](https://github.com/TanStack/query) 5 | tải dữ liệu, cache, làm mới định kỳ | MIT |
| [TanStack Table](https://github.com/TanStack/table) 8 | bảng sắp xếp được (danh sách chuyên gia) | MIT |
| [Radix UI Primitives](https://github.com/radix-ui/primitives) (Tabs) | tab truy cập được (bàn phím/ARIA) | MIT |
| [qrcode-generator](https://github.com/kazuhikoarase/qrcode-generator) 1.4.4 (Kazuhiko Arase; tệp `app/src/vendor/qrcode-generator.js`, chỉ đổi dòng export) | vẽ mã QR từ `otpauth://` trong trình hướng dẫn bật TOTP (nạp lười, vẽ trong trình duyệt, không gửi đi đâu) | MIT |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) 4 | tiện ích CSS | MIT |
| [Vite](https://github.com/vitejs/vite) 8 | công cụ build | MIT |
| [lucide](https://github.com/lucide-icons/lucide) (lucide-react) | icon | ISC |
| [react-grid-layout](https://github.com/react-grid-layout/react-grid-layout) 2.x (kèm react-draggable, react-resizable) | lưới widget kéo-thả/đổi cỡ của trang Terminal | MIT |
| [html-to-image](https://github.com/bubkoo/html-to-image) | xuất ảnh PNG một widget | MIT |
| clsx, tailwind-merge | gộp class (mẫu `cn()` của shadcn/ui) | MIT |
| [Inter](https://github.com/rsms/inter) qua `@fontsource-variable/inter` | chữ giao diện (có tiếng Việt) | OFL-1.1 |
| [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) qua `@fontsource/jetbrains-mono` | chữ số/giá (đơn cách, tabular) | OFL-1.1 |
| [nginx-unprivileged](https://hub.docker.com/r/nginxinc/nginx-unprivileged) 1.27 | máy chủ web / reverse proxy | BSD-2-Clause |

**Biểu đồ chuyên nghiệp (agent B, 2026-10-12)** — không thêm gói npm mới (đều tự viết, công thức chuẩn công khai): loại biểu đồ Renko / Range / Line Break / Kagi / Point & Figure (`components/chart/charttypes.js`), công cụ vẽ mở rộng — kênh hồi quy tuyến tính, Pitchfork Andrews, Gann fan, sóng Elliott, vùng cung/cầu, cung/vùng thời gian Fibonacci, projection, anchored VWAP, volume profile (`drawings2.js`), lớp phủ phiên/lịch/tin/cảnh báo giá và ký hiệu X/O (`overlays.js`), tính chỉ báo trong **Web Worker** gốc của trình duyệt (`indWorker.js`), crosshair/time-range sync dùng API công khai của lightweight-charts (`setCrosshairPosition`, `setVisibleRange`, `takeScreenshot`). Khái niệm tham khảo từ TradingView/lightweight-charts plugin-examples (Apache-2.0) và tài liệu công khai của các phương pháp; không sao chép mã nguồn đóng.

Công cụ vẽ (đường xu hướng, tia, kênh, chữ nhật, Fibonacci, thước đo) dùng API Series Primitive chính thức của lightweight-charts (Apache-2.0), cùng cơ chế với `plugin-examples` của TradingView; mã tự viết trong `components/chart/drawings.js`. Đã xem xét nhưng không dùng: `technicalindicators` (MIT, ngừng cập nhật từ 2023), `trading-signals` (MIT, phụ thuộc big.js chậm), `lightweight-charts-indicators` (MIT, ~17 MB).

## Nguồn tham khảo thiết kế (KHÔNG sao chép mã)

- **shadcn/ui** (MIT): theo mẫu cấu trúc component (`cn()`, primitive + Tailwind) – tự viết lại nhỏ gọn cho dữ liệu của hệ thống này.
- **Hummingbot Dashboard** (Apache-2.0), **OpenBB** (Apache-2.0): tham khảo bố cục terminal/watchlist.
- **FreqUI** (Freqtrade, **GPL-3.0**), **Ghostfolio** (**AGPL-3.0**), **Wealthfolio** (**AGPL-3.0**): chỉ xem ý tưởng bố cục; **không** lấy mã vì giấy phép copyleft sẽ buộc phát hành lại toàn bộ dự án theo cùng giấy phép.

Giấy phép đầy đủ của từng gói nằm trong thư mục `node_modules/<gói>/` khi build và trong tệp LICENSE của gói đó.
