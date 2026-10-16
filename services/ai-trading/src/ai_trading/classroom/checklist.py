"""Checklist có thứ tự (do CODE điều khiển). Mỗi cụm ≤3 câu hỏi mẫu cố định (fallback khi LLM lỗi). quantitative = cần số."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    questions: tuple[str, ...]
    followup: str = "Bạn có thể nêu cụ thể hơn (số, ví dụ) không?"
    quantitative: bool = False
    required: bool = False


STEPS: tuple[Step, ...] = (
    Step("context", "Bối cảnh thị trường", (
        "Kịch bản này chỉ hoạt động trong bối cảnh nào (xu hướng lớn tăng/giảm/đi ngang, giai đoạn biến động)?",
        "Làm sao nhận ra bối cảnh đó trên biểu đồ (ví dụ giá so với EMA nào, cấu trúc đỉnh/đáy)?")),
    Step("symbol_tf", "Mã và khung thời gian", (
        "Áp dụng cho mã nào (ví dụ EURUSD) và khung nào (M15, H1, H4, D1)?",
        "Bạn quan sát chính ở khung nào và dùng khung lớn hơn để lọc không?"), "Hãy nêu rõ tên mã và khung (ví dụ EURUSD H1).", False, True),
    Step("formation", "Điều kiện hình thành (định lượng)", (
        "Kịch bản hình thành qua những bước nào, theo thứ tự?",
        "Mỗi bước tính bằng số: bao nhiêu nến, bao nhiêu ATR hoặc bao nhiêu % (ví dụ nhịp tăng 2 ATR trong 6 nến)?",
        "Tỷ lệ giữa các sóng/nhịp là bao nhiêu thì còn hợp lệ?"), "Hãy cho con số cụ thể: bao nhiêu nến, bao nhiêu ATR hoặc %?", True, True),
    Step("trigger", "Điểm kích hoạt vào lệnh (mô phỏng)", (
        "Chính xác điều gì xảy ra thì kịch bản kích hoạt (nến nào đóng cửa, phá mức nào)?",
        "Vào ở giá đóng cửa nến kích hoạt hay mở nến kế tiếp? Có chờ hồi lại không?"), "Nêu một điều kiện kích hoạt đo được trên nến đã đóng.", True, True),
    Step("invalidation", "Điều kiện HUỶ kịch bản", (
        "Khi nào kịch bản bị huỷ trước khi kích hoạt (giá vượt mức nào, quá bao nhiêu nến)?",
        "Sau khi vào lệnh, dấu hiệu nào cho thấy giả thuyết sai ngay cả khi chưa chạm SL?"), "Hãy nêu mức giá hoặc số nến cụ thể làm kịch bản vô hiệu.", True),
    Step("sl_tp", "SL / TP / quản lý lệnh", (
        "SL đặt ở đâu (ví dụ trên đỉnh 6 nến + 0,25 ATR, hoặc 1,5 ATR)?",
        "TP bao nhiêu R (ví dụ 1R, 2R), có chốt từng phần hay trailing không?",
        "Giữ tối đa bao nhiêu nến thì thoát?"), "Cho SL theo ATR hoặc đỉnh N nến, TP theo bội số R.", True, True),
    Step("sizing", "Khối lượng và rủi ro", (
        "Rủi ro mỗi lệnh bao nhiêu % vốn mô phỏng?",
        "Có giới hạn số lệnh đồng thời hoặc lỗ tối đa mỗi ngày không?"), "Nêu % rủi ro mỗi lệnh.", True),
    Step("filters", "Bộ lọc phiên / tin / biến động / spread", (
        "Phiên nào (giờ UTC) cho phép hoặc cấm? Có tránh tin mạnh không?",
        "Biến động (ATR) tối thiểu/tối đa để kịch bản có nghĩa?",
        "Spread tối đa chấp nhận được?"), "Nêu ít nhất một bộ lọc đo được (giờ, ATR hoặc spread).", True),
    Step("examples", "Ví dụ ĐÚNG và ví dụ SAI", (
        "Cho một ví dụ ĐÚNG điển hình (mã, khung, thời điểm hoặc mô tả nến).",
        "Cho một ví dụ trông GẦN GIỐNG nhưng KHÔNG vào lệnh, và vì sao loại?"), "Hãy nêu ít nhất một ví dụ cụ thể (mã, khung, thời điểm).", False),
    Step("failure", "Điều gì làm kịch bản thất bại", (
        "Những tình huống nào thường làm kịch bản thua?",
        "Bạn từng thấy chế độ thị trường nào kịch bản hoàn toàn vô dụng?"), "Nêu ít nhất một tình huống thất bại điển hình.", False),
    Step("symmetry", "Đối xứng buy/sell", (
        "Phiên bản đối xứng (buy) có áp dụng được không? Có điểm nào bất đối xứng (ví dụ RSI không đối xứng 70/30)?",), "Có áp dụng ngược lại không, và khác ở điểm nào?", False),
    Step("other_markets", "Khung / mã khác", (
        "Kịch bản có áp dụng cho khung hoặc mã khác không (và vì sao)?",), "Nêu khung/mã khác nếu có, hoặc nói rõ là không.", False),
    Step("rationale", "Lý do kinh tế / tâm lý", (
        "Vì sao kịch bản này có thể tạo lợi thế (cung-cầu, thanh khoản, hành vi đám đông)?",
        "Ai là bên thua tiền để bạn có lãi?"), "Hãy nêu cơ chế kinh tế hoặc tâm lý đứng sau.", False),
)
KEYS = tuple(s.key for s in STEPS)
BY_KEY = {s.key: s for s in STEPS}
REQUIRED = tuple(s.key for s in STEPS if s.required)
assert all(len(s.questions) <= 3 for s in STEPS)
