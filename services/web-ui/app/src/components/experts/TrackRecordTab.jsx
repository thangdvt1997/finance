import { useState } from "react";
import { FixedNote, MethodButton } from "./bits";
import Leaderboard from "./Leaderboard";
import ConsensusMap from "./ConsensusMap";
import ExpertFeed from "./ExpertFeed";
import ExpertDetail from "./ExpertDetail";
import { Seg } from "../ui";

const VIEWS = [{ value: "xh", label: "Bảng xếp hạng" }, { value: "dt", label: "Bản đồ đồng thuận" }, { value: "qd", label: "Quan điểm mới" }];

/** Khối "track record chuyên gia" gắn vào trang Chuyên gia (tab đầu). */
export default function TrackRecordTab() {
  const [view, setView] = useState("xh");
  const [open, setOpen] = useState(null);
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Seg value={view} onChange={setView} options={VIEWS} label="Chế độ xem" />
        <MethodButton className="ml-auto" />
      </div>
      {view === "xh" && <Leaderboard onOpen={setOpen} />}
      {view === "dt" && <ConsensusMap onOpenExpert={setOpen} />}
      {view === "qd" && <ExpertFeed onOpenExpert={setOpen} />}
      <ExpertDetail id={open} onClose={() => setOpen(null)} />
    </div>
  );
}
