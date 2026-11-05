import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api, setSignedOutHandler } from "@/api/client";
import type { Me } from "@/api/types";
import { setLanguage } from "@/i18n";

interface AuthState {
  me: Me | null;
  loading: boolean;
  isOwner: boolean;
  refetch: () => void;
}

const Ctx = createContext<AuthState>({ me: null, loading: true, isOwner: false, refetch: () => undefined });

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { i18n } = useTranslation();
  const query = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.get<Me>("/auth/me");
      } catch (err) {
        if (err instanceof ApiError && (err.status === 401 || err.code === "STAFF_DISABLED")) return null;
        throw err;
      }
    },
    staleTime: 5 * 60_000,
    retry: 1,
  });
  useEffect(() => {
    setSignedOutHandler(() => {
      qc.setQueryData<Me | null>(["me"], null);
    });
    return () => setSignedOutHandler(null);
  }, [qc]);
  const me = query.data ?? null;
  useEffect(() => {
    // The language choice is saved per user and applied on next login (PRD section 9).
    if (me?.user.language && me.user.language !== i18n.language) void setLanguage(me.user.language);
  }, [me?.user.language, i18n]);
  return (
    <Ctx.Provider value={{ me, loading: query.isLoading, isOwner: me?.user.role === "owner",
      refetch: () => void query.refetch() }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  return useContext(Ctx);
}
