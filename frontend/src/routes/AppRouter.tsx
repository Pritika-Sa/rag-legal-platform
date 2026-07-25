import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "../layouts/AppLayout";
import { AuthPage } from "../pages/AuthPage";
import { ClauseAnalysisPage } from "../pages/ClauseAnalysisPage";
import { ComparisonPage } from "../pages/ComparisonPage";
import { ContradictionPage } from "../pages/ContradictionPage";
import { DashboardPage } from "../pages/DashboardPage";
import { ResetPasswordPage } from "../pages/ResetPasswordPage";
import { RiskAnalysisPage } from "../pages/RiskAnalysisPage";
import { ProtectedRoute } from "./ProtectedRoute";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/clauses" element={<ClauseAnalysisPage />} />
        <Route path="/risk" element={<RiskAnalysisPage />} />
        <Route path="/contradiction" element={<ContradictionPage />} />
        <Route path="/comparison" element={<ComparisonPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
