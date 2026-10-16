import { useMemo, useState } from "react";
import { BookOpenText, LifeBuoy, Plug, Search } from "lucide-react";
import { PageHead, Panel } from "../components/ui";
import { EaGuide } from "./Profile";
import { t } from "../lib/i18n";

export const glossary = () => [
  [t("Balance (số dư)"), t("Tiền trong tài khoản sau khi đã chốt lãi/lỗ các lệnh đóng, chưa gồm lãi/lỗ của lệnh đang mở.")],
  [t("Equity (vốn)"), t("Balance cộng lãi/lỗ đang mở. Đây là giá trị tài khoản nếu đóng hết lệnh ngay lúc này (chưa tính phí).")],
  [t("Margin (ký quỹ)"), t("Phần vốn broker giữ lại làm tài sản đảm bảo cho các vị thế đang mở.")],
  [t("Free margin (margin trống)"), t("Equity trừ margin đang giữ. Là phần đệm để chịu lỗ và mở thêm lệnh.")],
  [t("Margin level (mức margin)"), t("Equity chia margin, tính theo %. Càng thấp càng gần bị broker đóng lệnh tự động. Ví dụ 400% = vốn gấp 4 lần margin.")],
  [t("Margin call / stop-out"), t("Margin call: broker cảnh báo khi mức margin chạm ngưỡng thấp. Stop-out: broker tự đóng lệnh khi chạm ngưỡng thấp hơn (thường 20% đến 50%, tuỳ broker).")],
  [t("Đòn bẩy hiệu dụng"), t("Tổng giá trị các vị thế chia cho vốn. 10x nghĩa là giá đi ngược 1% có thể làm vốn giảm khoảng 10%. Khác với đòn bẩy tối đa broker cho phép.")],
  [t("Lot"), t("Đơn vị khối lượng. 1 lot forex tiêu chuẩn = 100.000 đơn vị tiền tệ cơ sở; 0.01 lot = 1.000 đơn vị.")],
  [t("Pip / point"), t("Bước giá nhỏ nhất thường dùng để đo biến động. Với cặp 5 chữ số thập phân, 1 pip = 0.0001.")],
  [t("Spread"), t("Chênh lệch giữa giá bán (bid) và giá mua (ask). Là chi phí ngầm mỗi lần vào lệnh.")],
  [t("Swap"), t("Phí hoặc lãi khi giữ lệnh qua đêm do chênh lệch lãi suất giữa hai tiền tệ.")],
  [t("Stop Loss (SL) / Take Profit (TP)"), t("SL: mức giá tự đóng lệnh để giới hạn lỗ. TP: mức giá tự đóng lệnh để chốt lãi. Ứng dụng này chỉ hiển thị, không đặt hay sửa SL/TP.")],
  [t("Lệnh chờ"), t("Lệnh đặt trước, chỉ khớp khi giá chạm mức đã đặt: Buy Limit / Sell Limit (vào khi giá quay lại) và Buy Stop / Sell Stop (vào khi giá phá qua).")],
  [t("Win rate (tỷ lệ thắng)"), t("Số lệnh lãi chia tổng số lệnh. Chỉ có ý nghĩa khi xem cùng mức lãi/lỗ trung bình mỗi lệnh.")],
  [t("Profit factor"), t("Tổng lãi gộp chia tổng lỗ gộp. Trên 1 là có lãi; thường từ 1,3 trở lên mới được coi là ổn.")],
  [t("Expectancy (kỳ vọng)"), t("Lãi/lỗ trung bình mỗi lệnh theo lịch sử. Dương nghĩa là hệ thống giao dịch của bạn đang có lợi thế.")],
  [t("Payoff ratio"), t("Lãi trung bình lệnh thắng chia lỗ trung bình lệnh thua.")],
  [t("R-multiple"), t("Lãi/lỗ của lệnh tính theo số lần rủi ro ban đầu (khoảng cách tới SL). +2R nghĩa là lãi gấp đôi mức bạn sẵn sàng lỗ.")],
  [t("Drawdown (sụt giảm)"), t("Mức vốn đã giảm so với đỉnh gần nhất. Max drawdown là lần sụt sâu nhất. Sụt 50% cần lãi 100% để gỡ lại.")],
  [t("VaR 95%"), t("Ước tính từ lịch sử: trong một ngày bình thường, 95% khả năng bạn không lỗ quá mức này. Ngày bất thường có thể tệ hơn.")],
  [t("Expected Shortfall (ES)"), t("Mức lỗ trung bình trong những ngày xấu nhất (5% ngày tệ nhất). Phản ánh rủi ro đuôi tốt hơn VaR.")],
  [t("Stress test"), t("Dựng lại những biến động lớn trong quá khứ trên các vị thế hiện tại để xem có thể lỗ bao nhiêu.")],
  [t("EA (Expert Advisor)"), t("Chương trình chạy trong MT4/MT5. Ở đây EA chỉ đọc dữ liệu tài khoản và gửi về hệ thống, không đặt lệnh.")],
  [t("Magic number"), t("Số nhận dạng mà EA/robot gắn vào lệnh để phân biệt lệnh của từng chiến lược.")],
  [t("Hedging / netting"), t("Hedging: được giữ đồng thời lệnh mua và bán cùng một mã. Netting: các lệnh cùng mã gộp thành một vị thế ròng.")],
  [t("MAE / MFE"), t("Mức đi ngược tối đa / mức đi thuận tối đa của giá trong lúc giữ lệnh. Giúp xem SL/TP có hợp lý không.")],
  [t("Cửa sổ rủi ro tin"), t("Khoảng thời gian quanh tin kinh tế lớn, khi giá dễ biến động mạnh và spread giãn rộng.")],
];

const faq = () => [
  [t("Ứng dụng có đặt lệnh giúp tôi không?"), t("Không. Hệ thống chỉ theo dõi và phân tích. Nó không có chức năng đặt, sửa hay đóng lệnh trên tài khoản của bạn.")],
  [t("Vì sao số liệu của tôi không cập nhật?"), t("Số liệu đến từ EA gắn trong MT4/MT5. Kiểm tra MT còn mở, EA còn gắn trên biểu đồ, bật Allow WebRequest cho địa chỉ ứng dụng. Chấm trạng thái ở đầu trang cho biết dữ liệu mới nhất đến cách đây bao lâu.")],
  [t("Cảnh báo có chạy khi tôi đóng ứng dụng không?"), t("Cảnh báo bạn tạo ở mục Cảnh báo chạy trên thiết bị nên chỉ hoạt động khi ứng dụng đang mở (kể cả tab nền). Cảnh báo chạy nền trên máy chủ đang chờ dịch vụ hỗ trợ.")],
  [t("Dữ liệu của tôi có bị người khác xem được không?"), t("Không. Mỗi tài khoản chỉ thấy dữ liệu của chính mình. Dữ liệu tài khoản không được lưu trong bộ nhớ ngoại tuyến của ứng dụng.")],
  [t("Tôi quên mật khẩu cổng?"), t("Liên hệ quản trị viên để được cấp lại mã. Mật khẩu cổng không phải mật khẩu giao dịch MT.")],
  [t("Vì sao một số mục chưa có dữ liệu?"), t("Một số tính năng cần đủ lịch sử (ví dụ VaR cần vài chục ngày vốn, thống kê cần các lệnh đã đóng). Khi có dữ liệu chúng sẽ tự xuất hiện.")],
];

export default function Help() {
  const [q, setQ] = useState("");
  const list = useMemo(() => { const needle = q.trim().toLowerCase(); return glossary().filter(([k, v]) => !needle || k.toLowerCase().includes(needle) || v.toLowerCase().includes(needle)); }, [q]);
  return (
    <>
      <PageHead title={t("Trợ giúp & thuật ngữ")} sub={t("Giải thích từng khối số liệu, thuật ngữ giao dịch và cách gắn EA.")} />
      <Panel title={t("Câu hỏi thường gặp")} icon={LifeBuoy}>
        <div className="grid gap-1">
          {faq().map(([ttl, d]) => (
            <details key={ttl} className="rounded-lg border border-line bg-panel2 px-3">
              <summary className="min-h-[44px] flex items-center cursor-pointer font-semibold text-[13.5px]">{ttl}</summary>
              <p className="m-0 pb-3 text-[13px] text-muted">{d}</p>
            </details>))}
        </div>
      </Panel>
      <Panel title={t("Thuật ngữ")} icon={BookOpenText}>
        <label className="label mb-3"><span className="sr-only">{t("Tìm thuật ngữ")}</span>
          <div className="relative"><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" /><input className="field !pl-9" placeholder={t("Tìm thuật ngữ, ví dụ margin")} value={q} onChange={(e) => setQ(e.target.value)} /></div></label>
        {list.length === 0 ? <p className="m-0 text-muted">{t("Không có thuật ngữ phù hợp.")}</p> : (
          <dl className="m-0 grid gap-2.5">
            {list.map(([k, v]) => <div key={k} className="grid gap-0.5 border-b border-line pb-2.5 last:border-0"><dt className="font-semibold text-[13.5px]">{k}</dt><dd className="m-0 text-[13px] text-muted">{v}</dd></div>)}
          </dl>
        )}
      </Panel>
      <Panel title={t("Cài EA trên MT4/MT5")} icon={Plug}><EaGuide /></Panel>
    </>
  );
}
