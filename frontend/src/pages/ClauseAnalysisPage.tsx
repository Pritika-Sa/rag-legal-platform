import { Alert, Box, CircularProgress, Grid, MenuItem, TextField, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import { PageHeader } from "../components/common/PageHeader";
import { MetricCard } from "../components/dashboard/MetricCard";
import { ClauseCard } from "../components/clauses/ClauseCard";
import { useClausesQuery } from "../hooks/useClauses";
import { useActiveDocumentStore } from "../store/activeDocumentStore";

const RISK_LEVELS = ["All", "High", "Medium", "Low", "None"];
const IMPORTANCE_LEVELS = ["All", "Critical", "Important", "Informational"];

// Direct port of views/clause_analysis.py::render() — same KPI row, same
// four filters (client-side, exactly like the original's plain-Python list
// filtering), same per-clause card.
export function ClauseAnalysisPage() {
  const { activeDocId, activeDocName } = useActiveDocumentStore();
  const clausesQuery = useClausesQuery(activeDocId);

  const [classFilter, setClassFilter] = useState("All");
  const [riskFilter, setRiskFilter] = useState("All");
  const [importanceFilter, setImportanceFilter] = useState("All");
  const [search, setSearch] = useState("");

  const clauses = clausesQuery.data ?? [];

  const classifications = useMemo(
    () => ["All", ...Array.from(new Set(clauses.map((c) => c.classification).filter((v): v is string => !!v))).sort()],
    [clauses],
  );

  const filtered = useMemo(() => {
    let result = clauses;
    if (classFilter !== "All") result = result.filter((c) => c.classification === classFilter);
    if (riskFilter !== "All") result = result.filter((c) => (c.risk_level || "None") === riskFilter);
    if (importanceFilter !== "All") result = result.filter((c) => c.importance_category === importanceFilter);
    if (search) {
      const needle = search.toLowerCase();
      result = result.filter(
        (c) =>
          (c.section_name || "").toLowerCase().includes(needle) ||
          (c.text_content || "").toLowerCase().includes(needle),
      );
    }
    return result;
  }, [clauses, classFilter, riskFilter, importanceFilter, search]);

  const highRiskCount = clauses.filter((c) => c.risk_level === "High").length;
  const importanceScores = clauses.map((c) => c.importance_score).filter((v): v is number => v !== null);
  const avgImportance = importanceScores.length
    ? Math.round(importanceScores.reduce((sum, v) => sum + v, 0) / importanceScores.length)
    : 0;

  return (
    <>
      <PageHeader
        icon="🔍"
        title="Clause Analysis"
        subtitle="Detailed clause-level analysis of the active document"
        badge="Agents 2 · 3 · 6 · 7"
        docName={activeDocName}
      />

      {!activeDocId && (
        <Alert severity="warning">Please select an active document in the sidebar or upload one to begin.</Alert>
      )}

      {activeDocId && clausesQuery.isLoading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      )}

      {activeDocId && clausesQuery.isError && (
        <Alert severity="error">Failed to load clauses for this document.</Alert>
      )}

      {activeDocId && clausesQuery.isSuccess && clauses.length === 0 && (
        <Alert severity="info">No clauses parsed for this document.</Alert>
      )}

      {activeDocId && clauses.length > 0 && (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 12, sm: 4 }}>
              <MetricCard icon="📑" label="Total Clauses" value={clauses.length} />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <MetricCard icon="🔴" label="High Risk Clauses" value={highRiskCount} accent="error.main" />
            </Grid>
            <Grid size={{ xs: 12, sm: 4 }}>
              <MetricCard icon="🎯" label="Avg Importance" value={`${avgImportance}/100`} />
            </Grid>
          </Grid>

          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 12, sm: 3 }}>
              <TextField select fullWidth size="small" label="Clause Type" value={classFilter} onChange={(e) => setClassFilter(e.target.value)}>
                {classifications.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              <TextField select fullWidth size="small" label="Risk Level" value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)}>
                {RISK_LEVELS.map((r) => (
                  <MenuItem key={r} value={r}>
                    {r}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              <TextField
                select
                fullWidth
                size="small"
                label="Importance Level"
                value={importanceFilter}
                onChange={(e) => setImportanceFilter(e.target.value)}
              >
                {IMPORTANCE_LEVELS.map((i) => (
                  <MenuItem key={i} value={i}>
                    {i}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              <TextField
                fullWidth
                size="small"
                label="Search title or text"
                placeholder="e.g. termination, liability…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </Grid>
          </Grid>

          <Typography variant="body2" sx={{ mb: 2 }}>
            Showing <strong>{filtered.length}</strong> of <strong>{clauses.length}</strong> clauses:
          </Typography>

          {activeDocId && filtered.map((clause) => (
            <ClauseCard key={clause.id} docId={activeDocId} clause={clause} />
          ))}
        </>
      )}
    </>
  );
}
