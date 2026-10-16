// Terminal tin tức (thay trang Tin tức cũ; đường dẫn #/tin-tuc giữ nguyên). Thành phần ở components/intel/NewsTerminal.jsx.
import { PageHead } from "../components/ui";
import NewsTerminalView from "../components/intel/NewsTerminal";

export default function News() {
  return (
    <>
      <PageHead title="Terminal tin tức" sub="Dòng tin thời gian thực, tìm toàn văn, lọc theo mã / chủ đề / mức quan trọng / cảm xúc. Cảm xúc, chủ đề và mức quan trọng do mô hình tự động gắn (tham khảo)." />
      <NewsTerminalView />
    </>
  );
}
