import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { router } from "./router";
import { AccountGate } from "./components/AccountGate";
import "./index.css";

// 先确认网站身份，再在 AccountGate 内预热本人 AI 配置，最后挂载页面。

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <AccountGate><RouterProvider router={router} /></AccountGate>
      <Toaster position="bottom-right" theme="dark" richColors closeButton duration={3500} />
    </ErrorBoundary>
  </StrictMode>
);
