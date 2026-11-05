import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { StepUpProvider } from "@/components/StepUp";
import { ListSkeleton } from "@/components/ui/states";
import { useAuth } from "@/hooks/useAuth";
import { HomePage } from "@/pages/Home";
import { LoginPage } from "@/pages/Login";
import { NotFoundPage } from "@/pages/NotFound";

// Less-used screens load on demand so the first screen stays fast on 4G.
const BorrowersPage = lazy(() => import("@/pages/Borrowers").then((m) => ({ default: m.BorrowersPage })));
const BorrowerDetailPage = lazy(() => import("@/pages/BorrowerDetail").then((m) => ({ default: m.BorrowerDetailPage })));
const BorrowerForm = lazy(() => import("@/pages/BorrowerForm").then((m) => ({ default: m.BorrowerForm })));
const LoansPage = lazy(() => import("@/pages/Loans").then((m) => ({ default: m.LoansPage })));
const LoanDetailPage = lazy(() => import("@/pages/LoanDetail").then((m) => ({ default: m.LoanDetailPage })));
const NewLoanPage = lazy(() => import("@/pages/NewLoan").then((m) => ({ default: m.NewLoanPage })));
const ReportsPage = lazy(() => import("@/pages/Reports").then((m) => ({ default: m.ReportsPage })));
const SettingsPage = lazy(() => import("@/pages/Settings").then((m) => ({ default: m.SettingsPage })));
const ImportPage = lazy(() => import("@/pages/Import").then((m) => ({ default: m.ImportPage })));
const AuditPage = lazy(() => import("@/pages/Audit").then((m) => ({ default: m.AuditPage })));

function Protected({ children, owner }: { children: ReactNode; owner?: boolean }) {
  const { me, loading, isOwner } = useAuth();
  // The shell renders straight away (no full-page swap, no layout shift); pages show their own
  // skeletons, and the server still refuses every call until the session is confirmed.
  if (!loading && !me) return <Navigate to="/login" replace />;
  if (owner && !loading && !isOwner) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export function App() {
  const { me } = useAuth();
  return (
    <StepUpProvider totpEnabled={!!me?.user.totp_enabled}>
      <Suspense fallback={<div className="p-6"><ListSkeleton rows={3} /></div>}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<Protected><AppShell /></Protected>}>
            <Route index element={<HomePage />} />
            <Route path="borrowers" element={<BorrowersPage />} />
            <Route path="borrowers/new" element={<BorrowerForm />} />
            <Route path="borrowers/:id" element={<BorrowerDetailPage />} />
            <Route path="borrowers/:id/edit" element={<BorrowerForm />} />
            <Route path="loans" element={<LoansPage />} />
            <Route path="loans/new" element={<NewLoanPage />} />
            <Route path="loans/:id" element={<LoanDetailPage />} />
            <Route path="reports" element={<Protected owner><ReportsPage /></Protected>} />
            <Route path="import" element={<Protected owner><ImportPage /></Protected>} />
            <Route path="audit" element={<Protected owner><AuditPage /></Protected>} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </Suspense>
    </StepUpProvider>
  );
}
