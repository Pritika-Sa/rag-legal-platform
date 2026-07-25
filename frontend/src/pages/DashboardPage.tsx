import { Alert, Box, CircularProgress, Grid, Stack, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/common/PageHeader";
import { PlotlyChart } from "../components/common/PlotlyChart";
import { MetricCard } from "../components/dashboard/MetricCard";
import { useDashboardQuery } from "../hooks/useDocuments";
import { useActiveDocumentStore } from "../store/activeDocumentStore";

const RISK_LEVELS = ["High", "Medium", "Low", "None"] as const;

// Direct port of views/dashboard.py::render() — same metric cards (with the
// same click-through targets), same two charts, same "no active document"
// and "no clauses yet" guards.
export function DashboardPage() {
  const { activeDocId, activeDocName } = useActiveDocumentStore();
  const navigate = useNavigate();
  const dashboardQuery = useDashboardQuery(activeDocId);

  return (
    <>
      <PageHeader
        icon="📊"
        title="Platform Dashboard"
        subtitle="Next-generation AI legal intelligence platform"
        badge="Overview"
        docName={activeDocName}
      />

      {!activeDocId && (
        <Alert severity="warning">
          Please select an active document in the sidebar to view its dashboard metrics.
        </Alert>
      )}

      {activeDocId && dashboardQuery.isLoading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      )}

      {activeDocId && dashboardQuery.isError && (
        <Alert severity="error">Failed to load dashboard metrics for this document.</Alert>
      )}

      {activeDocId && dashboardQuery.data && (
        <>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <MetricCard
                icon="📑"
                label="Total Clauses"
                value={dashboardQuery.data.total_clauses}
                onClick={() => navigate("/clauses")}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <MetricCard
                icon="⚠️"
                label="Risky Clauses (High/Med)"
                value={dashboardQuery.data.risky_clauses}
                onClick={() => navigate("/risk")}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <MetricCard
                icon="⚡"
                label="Contradictions"
                value={dashboardQuery.data.total_contradictions}
                onClick={() => navigate("/contradiction")}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <MetricCard icon="📄" label="Document Type" value={dashboardQuery.data.document_type} accent="success.main" />
            </Grid>
          </Grid>

          <Box sx={{ borderTop: "1px solid", borderColor: "divider", my: 3 }} />

          {dashboardQuery.data.radar_chart && dashboardQuery.data.bar_chart ? (
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 6 }}>
                <PlotlyChart figure={dashboardQuery.data.radar_chart} />
                <RiskDistributionBullets distribution={dashboardQuery.data.risk_distribution} />
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                <PlotlyChart figure={dashboardQuery.data.bar_chart} />
              </Grid>
            </Grid>
          ) : (
            <Alert severity="info">Upload and parse a document to view risk distributions.</Alert>
          )}
        </>
      )}
    </>
  );
}

function RiskDistributionBullets({ distribution }: { distribution: Record<string, number> }) {
  const total = RISK_LEVELS.reduce((sum, level) => sum + (distribution[level] ?? 0), 0);

  return (
    <Stack sx={{ mt: 1 }}>
      {RISK_LEVELS.map((level) => {
        const count = distribution[level] ?? 0;
        const pct = total ? Math.round((100 * count) / total) : 0;
        return (
          <Typography key={level} variant="body2">
            <strong>{level} Risk:</strong> {count} clause{count !== 1 ? "s" : ""} ({pct}%)
          </Typography>
        );
      })}
    </Stack>
  );
}
