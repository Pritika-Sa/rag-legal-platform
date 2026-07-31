import { Alert, Box, Button, CircularProgress, Grid, MenuItem, TextField, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import { PageHeader } from "../components/common/PageHeader";
import { S } from "../components/common/S";
import { MetricCard } from "../components/dashboard/MetricCard";
import { ClauseCard } from "../components/clauses/ClauseCard";
import { StructuredFieldCard } from "../components/clauses/StructuredFieldCard";
import { useClausesQuery } from "../hooks/useClauses";
import { useStaticText } from "../hooks/useStaticText";
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
  const [showStructuredFields, setShowStructuredFields] = useState(false);
  const searchPlaceholder = useStaticText("e.g. termination, liability…");

  const clauses = clausesQuery.data ?? [];

  // 2026-07-27: mirrors database/crud.py::get_dashboard_metrics' already-fixed
  // total_clauses -- structured/metadata fields (classification="Structured
  // Field", e.g. Policy Number, IDV, Nominee Name) are real, displayable
  // records, but were inflating this page's own "Total Clauses" KPI
  // independently of the dashboard's count, producing two different clause
  // counts for the same document on two pages. The full `clauses` array
  // (all 77) stays exactly as-is below for the classification filter and
  // the browsable list -- only this headline count is corrected.
  const legalClauses = useMemo(() => clauses.filter((c) => c.classification !== "Structured Field"), [clauses]);
  const structuredFieldClauses = useMemo(
    () => clauses.filter((c) => c.classification === "Structured Field"),
    [clauses],
  );

  // "Structured Field" is deliberately excluded here -- it has its own
  // dedicated "View Structured Fields" button below instead of being one
  // more option buried in this dropdown, so the Clause Type filter only
  // ever lists genuine legal clause categories.
  const classifications = useMemo(
    () => [
      "All",
      ...Array.from(new Set(legalClauses.map((c) => c.classification).filter((v): v is string => !!v))).sort(),
    ],
    [legalClauses],
  );

  // The Clause Type dropdown only ever offers legal categories (see
  // classifications above), so this filter's base pool is always
  // legalClauses -- Structured Field has its own separate view entirely.
  const filtered = useMemo(() => {
    let result = legalClauses;
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
  }, [legalClauses, classFilter, riskFilter, importanceFilter, search]);

  const filteredStructuredFields = useMemo(() => {
    if (!search) return structuredFieldClauses;
    const needle = search.toLowerCase();
    return structuredFieldClauses.filter(
      (c) =>
        (c.section_name || "").toLowerCase().includes(needle) ||
        (c.text_content || "").toLowerCase().includes(needle),
    );
  }, [structuredFieldClauses, search]);

  // Both stats now read from legalClauses, not the raw clauses array, for
  // the same reason the "Total Clauses" KPI does (see legalClauses above):
  // a structured field carries no real legal risk or importance, and for
  // documents processed before this fix existed, its stale risk_level could
  // still be a leftover "High"/"Medium" from when it was risk-scored as if
  // it were a legal clause.
  const highRiskCount = legalClauses.filter((c) => c.risk_level === "High").length;
  const importanceScores = legalClauses.map((c) => c.importance_score).filter((v): v is number => v !== null);
  const avgImportance = importanceScores.length
    ? Math.round(importanceScores.reduce((sum, v) => sum + v, 0) / importanceScores.length)
    : 0;

  return (
    <>
      <PageHeader
        icon="🔍"
        title="Clause Analysis"
        subtitle="Detailed clause-level analysis of the active document"

        docName={activeDocName}
      />

      {!activeDocId && (
        <Alert severity="warning"><S text="Please select an active document in the sidebar or upload one to begin." /></Alert>
      )}

      {activeDocId && clausesQuery.isLoading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      )}

      {activeDocId && clausesQuery.isError && (
        <Alert severity="error"><S text="Failed to load clauses for this document." /></Alert>
      )}

      {activeDocId && clausesQuery.isSuccess && clauses.length === 0 && (
        <Alert severity="info"><S text="No clauses parsed for this document." /></Alert>
      )}

      {activeDocId && clauses.length > 0 && (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 12, sm: 4 }}>
              <MetricCard icon="📑" label="Total Clauses" value={legalClauses.length} />
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
              <TextField
                select
                fullWidth
                size="small"
                label={<S text="Clause Type" />}
                value={classFilter}
                onChange={(e) => setClassFilter(e.target.value)}
                disabled={showStructuredFields}
              >
                {classifications.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c === "All" ? <S text="All" /> : c}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              <TextField
                select
                fullWidth
                size="small"
                label={<S text="Risk Level" />}
                value={riskFilter}
                onChange={(e) => setRiskFilter(e.target.value)}
                disabled={showStructuredFields}
              >
                {RISK_LEVELS.map((r) => (
                  <MenuItem key={r} value={r}>
                    <S text={r} />
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              <TextField
                select
                fullWidth
                size="small"
                label={<S text="Importance Level" />}
                value={importanceFilter}
                onChange={(e) => setImportanceFilter(e.target.value)}
                disabled={showStructuredFields}
              >
                {IMPORTANCE_LEVELS.map((i) => (
                  <MenuItem key={i} value={i}>
                    <S text={i} />
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              {/* Deliberately its own button, not a "Structured Field" option
                  inside the Clause Type dropdown above -- structured/metadata
                  fields (Policy Number, IDV, Nominee Name, ...) are a
                  different KIND of content from legal clauses, not one more
                  clause type to filter by, so they get their own view. */}
              <Button
                fullWidth
                size="small"
                variant={showStructuredFields ? "contained" : "outlined"}
                onClick={() => setShowStructuredFields((v) => !v)}
                sx={{ height: "40px" }}
              >
                {showStructuredFields ? (
                  <>◀ <S text="Back to Clauses" /></>
                ) : (
                  <>
                    🗂 <S text="View Structured Fields" /> ({structuredFieldClauses.length})
                  </>
                )}
              </Button>
            </Grid>
            <Grid size={{ xs: 12, sm: 3 }}>
              <TextField
                fullWidth
                size="small"
                label={showStructuredFields ? <S text="Search field label or value" /> : <S text="Search title or text" />}
                placeholder={searchPlaceholder}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </Grid>
          </Grid>

          {showStructuredFields ? (
            <>
              <Typography variant="body2" sx={{ mb: 2 }}>
                <S text="Showing" /> <strong>{filteredStructuredFields.length}</strong> <S text="of" />{" "}
                <strong>{structuredFieldClauses.length}</strong> <S text="structured field(s) — policy/metadata values, not legal clauses:" />
              </Typography>
              {filteredStructuredFields.length === 0 ? (
                <Alert severity="info"><S text="No structured fields match your search." /></Alert>
              ) : (
                filteredStructuredFields.map((clause) => <StructuredFieldCard key={clause.id} clause={clause} />)
              )}
            </>
          ) : (
            <>
              <Typography variant="body2" sx={{ mb: 2 }}>
                <S text="Showing" /> <strong>{filtered.length}</strong> <S text="of" /> <strong>{legalClauses.length}</strong> <S text="clauses:" />
              </Typography>
              {activeDocId && filtered.map((clause) => (
                <ClauseCard key={clause.id} docId={activeDocId} clause={clause} />
              ))}
            </>
          )}
        </>
      )}
    </>
  );
}
