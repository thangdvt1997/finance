// Ghi chú phiên bản hiển thị ở Trợ giúp > Ghi chú phiên bản. Thêm mục mới ở ĐẦU mảng.
export const VERSION = typeof __APP_VERSION__ !== "undefined" ? __APP_VERSION__ : "dev";
export const BUILD_TIME = typeof __BUILD_TIME__ !== "undefined" ? __BUILD_TIME__ : "";

export const CHANGELOG = [
  { v: "0.2.0", date: "2026-10-12", title: "Hệ thống trải nghiệm xuyên suốt", items: [
    "Tìm nhanh Ctrl K đời mới: tìm trang, mã (mở biểu đồ, thêm danh sách theo dõi, tạo cảnh báo), tin, thuật ngữ, lệnh nhanh, lịch sử gần đây; cú pháp “cảnh báo eurusd 1.0850”, “eurusd h4” và tiền tố > $ # ?.",
    "Trang Cài đặt: giao diện sáng/tối/tự động, 6 màu nhấn, mật độ, cỡ chữ, tương phản cao, giảm chuyển động, múi giờ, kiểu ngày/số/tiền, màu tăng-giảm (có chế độ cho người mù màu); lưu theo tài khoản.",
    "Trung tâm thông báo (chuông): gom cảnh báo, tin quan trọng, tín hiệu chuyên gia, sự cố hệ thống; lọc, đánh dấu đã đọc, toast, âm báo, thông báo trình duyệt.",
    "Hướng dẫn làm quen lần đầu, tooltip thuật ngữ, trang Trợ giúp (thuật ngữ, câu hỏi thường gặp, ghi chú phiên bản) và trang Giới thiệu.",
    "Trạng thái chuẩn: khung tải cho bảng/biểu đồ, trạng thái rỗng có hướng dẫn, lỗi có chẩn đoán và thử lại, banner mất kết nối tự nối lại.",
    "Công cụ trang: xuất CSV/Excel, ảnh PNG, in/lưu PDF, sao chép bảng, sao chép liên kết giữ trạng thái, đánh dấu trang.",
    "Trợ năng: vùng cuộn dùng được bằng bàn phím, mũi tên trong bảng, vùng thông báo cho trình đọc màn hình, kiểm tra tương phản ở cả hai giao diện.",
    "Trang Design system nội bộ (#/design) liệt kê màu, chữ, thành phần.",
  ] },
  { v: "0.1.x", date: "trước 12/10/2026", title: "Nền tảng giao diện", items: [
    "Tổng quan, Thị trường (biểu đồ nến chuyên nghiệp, chỉ báo, công cụ vẽ), Chứng khoán VN, Danh sách theo dõi, Phân tích.",
    "Bản tin AI, Tin tức, Lịch kinh tế, Chuyên gia.",
    "Tài khoản MT4/MT5 chỉ-đọc, Mô phỏng, Nhật ký giao dịch, Cảnh báo theo luật người dùng, Báo cáo ngày/tuần.",
    "Quản lý khách hàng, đăng nhập master/khách hàng, ứng dụng cài được (PWA), băng giá và đồng hồ phiên giao dịch.",
  ] },
];
