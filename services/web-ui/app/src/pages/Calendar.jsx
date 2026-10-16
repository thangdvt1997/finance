// Lịch kinh tế chuyên nghiệp (thay trang cũ; đường dẫn #/lich giữ nguyên). Thành phần ở components/intel/CalendarPro.jsx.
import { Disclaimer, PageHead } from "../components/ui";
import CalendarProView from "../components/intel/CalendarPro";

export default function Calendar() {
  return (
    <>
      <PageHead title="Lịch kinh tế" sub="Lưới tuần theo ngày (giờ Việt Nam), đếm ngược, màu “bất ngờ” theo tác động lên đồng tiền, cụm cửa sổ rủi ro, lịch sử thực tế–dự báo–kỳ trước và nhắc trước sự kiện." />
      <CalendarProView />
      <div>
        <Disclaimer>
          <b>Lưu ý.</b> Thực tế điền ngay khi công bố; dự báo/kỳ trước <b>chỉ dùng cá nhân/nội bộ, không phân phối lại</b>. Màu “bất ngờ” là tác động lên <i>đồng tiền</i> (xanh = tốt, đỏ = xấu), không phải lời khuyên giao dịch.
        </Disclaimer>
      </div>
    </>
  );
}
