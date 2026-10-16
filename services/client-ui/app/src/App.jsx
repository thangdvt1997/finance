import { Suspense, lazy } from "react";
import { LogOut, RefreshCw, ServerCrash, WalletCards } from "lucide-react";
import { useAuth } from "./lib/auth";
import { useRoute } from "./lib/router";
import { LOADERS } from "./lib/preload";
import { Notice, Skeleton } from "./components/ui";
import { Brand, Shell } from "./components/shell";
import ChangePasswordForm from "./components/changepw";
import Login from "./pages/Login";

const PAGES = Object.fromEntries(Object.entries(LOADERS).map(([k, f]) => [k, lazy(f)]));

function Splash({ children }) {
  return <main className="auth-wrap" id="main"><div className="auth-card rise text-center justify-items-center"><Brand />{children}</div></main>;
}

export default function App() {
  const a = useAuth();
  const { path, query } = useRoute();

  if (a.status === "loading") return <Splash><div className="w-full max-w-[260px]"><Skeleton rows={3} /></div><span className="sr-only">Đang kiểm tra phiên đăng nhập</span></Splash>;
  if (a.status === "down")
    return (
      <Splash>
        <ServerCrash size={30} className="text-down" aria-hidden="true" />
        <h1 className="m-0 text-[18px]">Chưa kết nối được dịch vụ đăng nhập</h1>
        <p className="m-0 text-muted text-[13.5px]">{a.error} Dịch vụ có thể đang khởi động lại, hãy thử lại sau ít phút.</p>
        <button className="btn primary" onClick={a.refresh}><RefreshCw size={16} aria-hidden="true" /> Thử lại</button>
      </Splash>
    );
  if (a.status === "anon") return <Login />;

  if (a.me.role === "master")
    return (
      <Splash>
        <h1 className="m-0 text-[18px]">Đây là ứng dụng dành cho khách hàng</h1>
        <p className="m-0 text-muted text-[13.5px]">Bạn đang đăng nhập bằng tài khoản quản trị. Hãy dùng giao diện quản trị để xem tất cả khách hàng. Đăng xuất để thử đăng nhập bằng ID MT của một khách hàng.</p>
        <button className="btn primary" onClick={() => a.logout()}><LogOut size={16} aria-hidden="true" /> Đăng xuất</button>
      </Splash>
    );

  if (a.me.mustChange)
    return (
      <main className="auth-wrap" id="main">
        <div className="auth-card rise">
          <div className="flex items-center gap-3"><Brand /><h1 className="m-0 text-[20px] font-bold">Đổi mật khẩu cổng</h1></div>
          <div className="panel panel-b"><ChangePasswordForm forced /></div>
          <button className="btn ghost self-start" onClick={() => a.logout()}><LogOut size={16} aria-hidden="true" /> Đăng xuất</button>
        </div>
      </main>
    );

  const Page = PAGES[path] || PAGES["/hom-nay"];
  const cur = PAGES[path] ? path : "/hom-nay";
  return (
    <Shell path={cur}>
      {a.accounts.length === 0 && cur !== "/ho-so" ? (
        <Notice tone="info" icon={WalletCards} title="Chưa có tài khoản MT nào được gán">
          Hồ sơ của bạn chưa gắn với tài khoản MT4/MT5. Hãy liên hệ quản trị viên để được cấp tài khoản và mã ghép cặp. Bạn vẫn có thể xem{" "}
          <a className="underline" href="#/thi-truong">Thị trường</a>, <a className="underline" href="#/tin-lich">Tin & Lịch</a> và <a className="underline" href="#/ho-so">Hồ sơ</a>.
        </Notice>
      ) : null}
      <Suspense fallback={<Skeleton rows={6} h={20} />}><Page query={query} key={`${cur}:${a.active?.id || ""}`} /></Suspense>
    </Shell>
  );
}
