import { Alert, Box, Button, CircularProgress, Grid, MenuItem, TextField, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import { Badge } from "../components/common/Badge";
import { PageHeader } from "../components/common/PageHeader";
import { PlotlyChart } from "../components/common/PlotlyChart";
import { S } from "../components/common/S";
import { T } from "../components/common/T";
import { MetricCard } from "../components/dashboard/MetricCard";
import { AuthenticityBreakdown } from "../components/risk/AuthenticityBreakdown";
import { FlaggedClauseCard } from "../components/risk/FlaggedClauseCard";
import {
  useQuickEstimateMutation,
  useRecomputeAuthenticityMutation,
  useRiskOverviewQuery,
  useRiskyClausesQuery,
} from "../hooks/useRisk";
import { useActiveDocumentStore } from "../store/activeDocumentStore";
import { AUTHENTICITY_LEVEL_COLORS } from "../utils/authenticityDisplay";
import { RISK_COLORS } from "../utils/clauseDisplay";

// Direct port of views/risk_analysis.py::render() — same Overview section
// (authenticity score/recompute/breakdown, quick-estimate gauge) and same
// Flagged Clauses section (filters, KPIs, per-clause cards).
export function RiskAnalysisPage() {
  const { activeDocId, activeDocName } = useActiveDocumentStore();
  const overviewQuery = useRiskOverviewQuery(activeDocId);
  const riskyClausesQuery = useRiskyClausesQuery(activeDocId);
  const recomputeMutation = useRecomputeAuthenticityMutation(activeDocId ?? -1);
  const quickEstimateMutation = useQuickEstimateMutation(activeDocId ?? -1);

  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState("All Categories");
  const [levelFilter, setLevelFilter] = useState("All Levels");

  const authenticity = recomputeMutation.data ?? overviewQuery.data;
  const riskyClauses = riskyClausesQuery.data ?? [];

  const categories = useMemo(
    () => Array.from(new Set(riskyClauses.map((c) => c.risk_category || "Uncategorized"))).sort(),
    [riskyClauses],
  );

  const filtered = useMemo(() => {
    let result = riskyClauses;
    if (categoryFilter !== "All Categories") {
      result = result.filter((c) => (c.risk_category || "Uncategorized") === categoryFilter);
    }
    if (levelFilter !== "All Levels") {
      result = result.filter((c) => c.risk_level === levelFilter);
    }
    return result;
  }, [riskyClauses, categoryFilter, levelFilter]);

  const highCount = riskyClauses.filter((c) => c.risk_level === "High").length;
  const medCount = riskyClauses.filter((c) => c.risk_level === "Medium").length;

  if (!activeDocId) {
    return (
      <>
        <PageHeader
          icon="⚠️"
          title="Risk Analysis & Mitigation Advisor"
          subtitle="A plain-English breakdown of document-wide risk and authenticity, plus every flagged clause explained."
        />
        <Alert severity="warning"><S text="Please select an active document in the sidebar to review risks." /></Alert>
      </>
    );
  }

  return (
    <>
      <PageHeader
        icon="⚠️"
        title="Risk Analysis & Mitigation Advisor"
        subtitle="A plain-English breakdown of document-wide risk and authenticity, plus every flagged clause explained."
        docName={activeDocName}
      />

      {/* Overview */}
      <Typography variant="h6" sx={{ mb: 1.5 }}>
        📊 <S text="Risk Overview" />
      </Typography>
      <Grid container spacing={2} sx={{ mb: 2, alignItems: "flex-start" }}>
        <Grid size={{ xs: 12, md: 6 }}>
          {overviewQuery.isLoading ? (
            <CircularProgress size={24} />
          ) : (
            <>
              <MetricCard
                icon="🔍"
                label="Authenticity Score"
                value={authenticity?.authenticity_score !== undefined && authenticity?.authenticity_score !== null ? `${authenticity.authenticity_score}/100` : "—"}
                accent={AUTHENTICITY_LEVEL_COLORS[authenticity?.authenticity_level ?? ""] ?? "#888888"}
              />
              {authenticity?.authenticity_score !== undefined && authenticity?.authenticity_score !== null && (
                <Box sx={{ textAlign: "center", mt: 1 }}>
                  <Badge
                    label={<S text={(authenticity.authenticity_level ?? "").toUpperCase()} />}
                    color={AUTHENTICITY_LEVEL_COLORS[authenticity.authenticity_level ?? ""] ?? "#888888"}
                  />
                </Box>
              )}

              <Button
                variant="outlined"
                fullWidth
                sx={{ mt: 1.5 }}
                onClick={() => recomputeMutation.mutate()}
                loading={recomputeMutation.isPending}
              >
                🔄 <S text="Recompute Authenticity" />
              </Button>
              {recomputeMutation.isError && <Alert severity="error" sx={{ mt: 1 }}><S text="Failed to recompute authenticity." /></Alert>}

              {authenticity?.authenticity_factors && authenticity.authenticity_factors.length > 0 && (
                <Box sx={{ mt: 1.5 }}>
                  <Button variant="text" size="small" onClick={() => setBreakdownOpen(!breakdownOpen)}>
                    {breakdownOpen ? <S text="Hide" /> : <>🔍 <S text="Authenticity Factor Breakdown" /></>}
                  </Button>
                  {breakdownOpen && (
                    <Box sx={{ mt: 1 }}>
                      <AuthenticityBreakdown
                        factors={authenticity.authenticity_factors}
                        documentType={authenticity.authenticity_document_type}
                        documentTypeConfidence={authenticity.authenticity_document_type_confidence}
                        confidence={authenticity.authenticity_confidence}
                      />
                    </Box>
                  )}
                </Box>
              )}
            </>
          )}
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 3, p: 2, textAlign: "center" }}>
            <Typography
              variant="caption"
              sx={{ opacity: 0.65, textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}
            >
              📊 <S text="Document Risk" />
            </Typography>
            <Button
              variant="contained"
              fullWidth
              sx={{ mt: 1.5, maxWidth: 260, mx: "auto", display: "block" }}
              onClick={() => quickEstimateMutation.mutate()}
              loading={quickEstimateMutation.isPending}
            >
              ⚡ <S text="Quick Estimate" />
            </Button>


            {quickEstimateMutation.isError && <Alert severity="error" sx={{ mt: 1 }}><S text="Failed to generate document risk score." /></Alert>}

            {quickEstimateMutation.data && (
              <Box sx={{ mt: 2 }}>
                <PlotlyChart figure={quickEstimateMutation.data.risk_gauge_chart} height={220} />
                <Box sx={{ mt: 1 }}>
                  <Badge
                    label={<S text={quickEstimateMutation.data.risk_level.toUpperCase()} />}
                    color={RISK_COLORS[quickEstimateMutation.data.risk_level] ?? "#888888"}
                  />
                </Box>
                <Typography variant="subtitle2" sx={{ mt: 1.5, textAlign: "left" }}>
                  <S text="Recommendations" />
                </Typography>
                <Typography variant="body2" sx={{ textAlign: "left" }}>
                  <T text={quickEstimateMutation.data.recommendations} />
                </Typography>
              </Box>
            )}
          </Box>
        </Grid>
      </Grid>

      {/* Flagged Clauses */}
      {riskyClausesQuery.isLoading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      )}

      {riskyClausesQuery.isSuccess && riskyClauses.length === 0 && (
        <Alert severity="success">✅ <S text="Excellent! No High or Medium risk clauses were detected in this agreement." /></Alert>
      )}

      {riskyClauses.length > 0 && (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                select
                fullWidth
                size="small"
                label={<>🏷 <S text="Category" /></>}
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
              >
                <MenuItem value="All Categories"><S text="All Categories" /></MenuItem>
                {categories.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                select
                fullWidth
                size="small"
                label={<>⚠ <S text="Risk Level" /></>}
                value={levelFilter}
                onChange={(e) => setLevelFilter(e.target.value)}
              >
                <MenuItem value="All Levels"><S text="All Levels" /></MenuItem>
                <MenuItem value="High"><S text="High" /></MenuItem>
                <MenuItem value="Medium"><S text="Medium" /></MenuItem>
              </TextField>
            </Grid>
          </Grid>

          {filtered.length === 0 ? (
            <Alert severity="info"><S text="No flagged clauses match the selected filters." /></Alert>
          ) : (
            <>
              <Grid container spacing={2} sx={{ mb: 2 }}>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <MetricCard icon="🚩" label="Flagged Clauses" value={riskyClauses.length} accent="error.main" />
                </Grid>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <MetricCard icon="🔴" label="High Risk" value={highCount} accent="error.main" />
                </Grid>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <MetricCard icon="🟡" label="Medium Risk" value={medCount} accent="warning.main" />
                </Grid>
              </Grid>

              {filtered.map((clause) => (
                <FlaggedClauseCard key={clause.id} clause={clause} />
              ))}
            </>
          )}
        </>
      )}
    </>
  );
}
