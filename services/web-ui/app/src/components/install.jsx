import { Download, RefreshCw } from "lucide-react";
import { applyUpdate, promptInstall, usePwa } from "../lib/pwa";

/** Nút "Cài đặt ứng dụng" — chỉ hiện khi trình duyệt cho phép (beforeinstallprompt) và chưa cài. */
export function InstallButton() {
  const { canInstall } = usePwa();
  if (!canInstall) return null;
  return (
    <button type="button" className="btn" onClick={promptInstall} title="Cài đặt thành ứng dụng trên thiết bị">
      <Download size={13} aria-hidden="true" /> <span className="hidden sm:inline">Cài đặt ứng dụng</span><span className="sm:hidden">Cài đặt</span>
    </button>
  );
}

/** Thông báo "Có bản mới" khi service worker mới đã sẵn sàng. */
export function UpdateToast() {
  const { updateReady } = usePwa();
  if (!updateReady) return null;
  return (
    <div role="status" aria-live="polite"
      className="fixed z-50 left-3 right-3 sm:left-auto sm:right-4 bottom-[max(0.75rem,env(safe-area-inset-bottom))] sm:w-[22rem] flex items-center gap-3 rounded-md border border-line2 bg-panel px-3 py-2 shadow-lg text-[12.5px]">
      <RefreshCw size={14} className="text-accent shrink-0" aria-hidden="true" />
      <span className="flex-1">Có bản mới của ứng dụng.</span>
      <button type="button" className="btn" onClick={applyUpdate}>Tải lại</button>
    </div>
  );
}
