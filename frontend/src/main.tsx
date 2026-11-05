import "./index.css";
import { i18nReady } from "./i18n";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { registerSW } from "virtual:pwa-register";

import { ApiError } from "@/api/client";
import { ToastProvider } from "@/components/ui/toast";
import { AuthProvider } from "@/hooks/useAuth";

import { App } from "./App";
import { UpdatePrompt, offerUpdate } from "./UpdatePrompt";

try {
  const theme = localStorage.getItem("lt-theme");
  if (theme) document.documentElement.dataset.theme = theme;
} catch {
  /* private mode */
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 24 * 60 * 60_000,
      refetchOnWindowFocus: true,
      retry: (count, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 2,
      networkMode: "offlineFirst",
    },
    mutations: { networkMode: "always" },
  },
});

const updateSW = registerSW({ onNeedRefresh: () => offerUpdate(() => void updateSW(true)) });

// Render after the saved language is ready, so the page never redraws in another language.
void i18nReady.finally(() => createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <AuthProvider>
            <App />
            <UpdatePrompt />
          </AuthProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
));
