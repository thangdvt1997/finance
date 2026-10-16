// Metadata của các trang có sẵn trước khi có cơ chế tự đăng ký. Trang MỚI không thêm vào đây:
// chỉ cần tạo `pages/<Tên>.jsx` có `export const meta = {...}` (xem docs/WIDGETS.md, mục "Trang").
import { LayoutDashboard, CandlestickChart, Newspaper, CalendarClock, Users, Wallet, BellRing, Activity, Gauge, FlaskConical, ListChecks, FileText, Landmark, BookOpen, UserCog, Sunrise } from "lucide-react";

const M = ["master"];
export const LEGACY = {
  Overview: { path: "tong-quan", label: "Tổng quan", group: "Thị trường", short: "Tổng quan", icon: LayoutDashboard, order: 20, roles: M },
  Market: { path: "thi-truong", label: "Thị trường", group: "Thị trường", icon: CandlestickChart, order: 30, roles: M, primary: true },
  ChungKhoanVN: { path: "chung-khoan-vn", label: "Chứng khoán VN", group: "Thị trường", short: "Chứng khoán", icon: Landmark, order: 40, roles: M, primary: true },
  Watchlist: { path: "danh-sach", label: "Danh sách theo dõi", group: "Thị trường", icon: ListChecks, order: 50, roles: M },
  Analytics: { path: "phan-tich", label: "Phân tích", group: "Thị trường", icon: Gauge, order: 60, roles: M },
  Briefing: { path: "ban-tin", label: "Bản tin", group: "Thông tin", icon: Sunrise, order: 10, roles: M },
  News: { path: "tin-tuc", label: "Tin tức", group: "Thông tin", icon: Newspaper, order: 20, roles: M },
  Calendar: { path: "lich", label: "Lịch kinh tế", group: "Thông tin", icon: CalendarClock, order: 30, roles: M },
  Experts: { path: "chuyen-gia", label: "Chuyên gia", group: "Thông tin", icon: Users, order: 40, roles: M },
  Accounts: { path: "tai-khoan", label: "Tài khoản", group: "Tài khoản", icon: Wallet, order: 10, roles: M },
  Paper: { path: "mo-phong", label: "Mô phỏng", group: "Tài khoản", icon: FlaskConical, order: 20, roles: M },
  Journal: { path: "nhat-ky", label: "Nhật ký", group: "Tài khoản", icon: BookOpen, order: 30, roles: M },
  Alerts: { path: "canh-bao", label: "Cảnh báo", group: "Vận hành", short: "Cảnh báo", icon: BellRing, order: 10, roles: M, primary: true },
  Reports: { path: "bao-cao", label: "Báo cáo", group: "Vận hành", icon: FileText, order: 20, roles: M },
  Clients: { path: "khach-hang", label: "Khách hàng", group: "Vận hành", short: "Khách hàng", icon: UserCog, order: 30, roles: M },
  System: { path: "he-thong", label: "Hệ thống", group: "Vận hành", icon: Activity, order: 40, roles: M },
};
