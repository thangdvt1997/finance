import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import App from "./App";
import { AuthProvider } from "./lib/auth";
import { PrefsProvider } from "./lib/prefs";
import { PrefSync } from "./lib/prefsync";
import { registerSW } from "./lib/pwa";
import { restoreCache, startPersist } from "./lib/persist";

// gcTime dài: quay lại trang vẫn thấy dữ liệu cũ ngay (stale-while-revalidate), rồi cập nhật ở nền.
const client = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: true, staleTime: 10_000, gcTime: 30 * 60_000 } } });
restoreCache(client).finally(() => startPersist(client));

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <PrefsProvider>
      <QueryClientProvider client={client}>
        <AuthProvider>
          <App />
          <PrefSync />
        </AuthProvider>
      </QueryClientProvider>
    </PrefsProvider>
  </StrictMode>,
);
registerSW();
