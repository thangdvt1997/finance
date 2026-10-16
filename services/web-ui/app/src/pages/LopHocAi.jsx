// Trang "AI Training Class" cho vai CHUYÊN GIA (expert): dạy AI + chạy test paper trong các phòng được mời. Master dùng tab "AI Training Class" trong AI Trading.
// CHỈ nghiên cứu/paper: không có đường đặt lệnh.
import { useState } from "react";
import { GraduationCap } from "lucide-react";
import { Disclaimer, PageHead, Seg } from "../components/ui";
import Classroom from "../components/classroom/Classroom";
import MethodsPage from "../components/classroom/MethodsPage";

export const meta = { path: "lop-hoc-ai", label: "AI Training Class", group: "Thị trường", icon: GraduationCap, order: 66, roles: ["expert"], primary: true, keywords: "ai training class lop hoc ai day kich ban chuyen gia chat phong" };

const LKEY = "ts-aitrading-lang";
export default function LopHocAi() {
  const [lang, setLang] = useState(() => { try { return localStorage.getItem(LKEY) === "en" ? "en" : "vi"; } catch { return "vi"; } });
  const ch = (l) => { setLang(l); try { localStorage.setItem(LKEY, l); } catch { /* bỏ */ } };
  const en = lang === "en";
  const [area, setArea] = useState(() => { try { return sessionStorage.getItem("cr-area") === "methods" ? "methods" : "rooms"; } catch { return "rooms"; } });
  const goArea = (a) => { setArea(a); try { sessionStorage.setItem("cr-area", a); } catch { /* bỏ */ } };
  return (
    <div className="grid gap-2">
      <PageHead title="AI Training Class" sub={en ? "Teach the AI a trading scenario. Research and paper only — no real orders." : "Dạy AI một kịch bản giao dịch. Chỉ nghiên cứu và mô phỏng (paper) — không đặt lệnh thật."}
        right={<Seg label="Language" value={lang} onChange={ch} options={[{ value: "vi", label: "VI" }, { value: "en", label: "EN" }]} />} />
      <Disclaimer>{en ? "Experts can teach and run paper tests in the rooms they were invited to. Results are honest: no-edge is a normal outcome." : "Chuyên gia chỉ dạy và chạy test paper trong các phòng được mời. Kết quả trung thực: không có edge là kết quả bình thường."}</Disclaimer>
      <Seg label={en ? "Area" : "Khu vực"} value={area} onChange={goArea} options={[{ value: "rooms", label: en ? "Rooms" : "Phòng kịch bản" }, { value: "methods", label: en ? "Methods" : "Phương pháp" }]} />
      {area === "methods" ? <MethodsPage lang={lang} onGoRooms={() => goArea("rooms")} /> : <Classroom lang={lang} />}
    </div>
  );
}
