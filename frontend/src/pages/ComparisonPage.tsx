import { Alert, Box, Button, Grid, MenuItem, TextField, Typography } from "@mui/material";
import { PageHeader } from "../components/common/PageHeader";
import { S } from "../components/common/S";
import { T } from "../components/common/T";
import { SideBySideView } from "../components/comparison/SideBySideView";
import { SimilarityGauge } from "../components/comparison/SimilarityGauge";
import { useDocumentsQuery } from "../hooks/useDocuments";
import { useInViewOnce } from "../hooks/useInViewOnce";
import { useCompareMutation } from "../hooks/useComparison";
import { extractErrorMessage } from "../api/authApi";
import { useComparisonStore } from "../store/comparisonStore";

// Direct port of views/comparison.py::render(). Doc-A/doc-B selection lives
// in comparisonStore (not the global active-document store) — separate from
// active_doc_id, matching the original's explicit "this module... never
// changes your globally active document" behavior, but still readable by
// the floating chat widget's comparison-scope picker (Phase 9), exactly
// like Streamlit's own keyed-widget session_state was.
export function ComparisonPage() {
  const documentsQuery = useDocumentsQuery();
  const documents = documentsQuery.data ?? [];
  const { docAId, docBId, setDocA, setDocB } = useComparisonStore();
  const compareMutation = useCompareMutation();
  // Each AI-generated result block translates only once it's actually
  // scrolled into view — mainly matters for the difference report, which
  // is long and sits below the fold on most screens.
  const [changeSummaryRef, changeSummaryVisible] = useInViewOnce<HTMLDivElement>();
  const [riskChangesRef, riskChangesVisible] = useInViewOnce<HTMLDivElement>();
  const [differenceReportRef, differenceReportVisible] = useInViewOnce<HTMLDivElement>();

  // Mirrors the original's default index=0 / index=1 selectbox defaults,
  // applied once documents finish loading.
  if (documents.length >= 2 && docAId === null && docBId === null) {
    setDocA(documents[0].id);
    setDocB(documents[1].id);
  }

  const handleCompare = () => {
    if (docAId === null || docBId === null) return;
    compareMutation.mutate({ docAId, docBId });
  };

  return (
    <>
      <PageHeader
        icon="🔀"
        title="Comparison Center"
        subtitle="Select two agreements to analyze structural differences, clause variations, and potential vulnerabilities between them. This module keeps its own document selection and never changes your globally active document."
      />

      {documentsQuery.isSuccess && documents.length < 2 && (
        <Alert severity="info"><S text="Please upload at least two documents to use Comparison Center." /></Alert>
      )}

      {documents.length >= 2 && (
        <>
          <Typography variant="subtitle1" sx={{ mb: 1.5 }}>
            <S text="Which documents would you like to compare?" />
          </Typography>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                select
                fullWidth
                label={<S text="Document 1:" />}
                value={docAId ?? ""}
                onChange={(e) => setDocA(Number(e.target.value))}
              >
                {documents.map((d) => (
                  <MenuItem key={d.id} value={d.id}>
                    {d.name}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField
                select
                fullWidth
                label={<S text="Document 2:" />}
                value={docBId ?? ""}
                onChange={(e) => setDocB(Number(e.target.value))}
              >
                {documents.map((d) => (
                  <MenuItem key={d.id} value={d.id}>
                    {d.name}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
          </Grid>

          {docAId !== null && docBId !== null && docAId === docBId && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              <S text="Please select two different documents to compare." />
            </Alert>
          )}

          <Button
            variant="contained"
            onClick={handleCompare}
            loading={compareMutation.isPending}
            disabled={docAId === null || docBId === null || docAId === docBId}
          >
            ⚖️ <S text="Compare Documents" />
          </Button>

          {compareMutation.isError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              <S text="Failed to compile comparison:" /> <T text={extractErrorMessage(compareMutation.error, "unknown error")} />
            </Alert>
          )}

          {compareMutation.data && (
            <Box sx={{ mt: 3 }}>
              <SimilarityGauge score={compareMutation.data.similarity_score} />

              <Typography variant="h6" sx={{ mt: 2 }}>
                📋 <S text="Change Summary" />
              </Typography>
              <Alert severity="info" sx={{ mt: 1 }} ref={changeSummaryRef}>
                {changeSummaryVisible ? <T text={compareMutation.data.change_summary} /> : compareMutation.data.change_summary}
              </Alert>

              <Grid container spacing={2} sx={{ mt: 1 }}>
                <Grid size={4}>
                  <Typography variant="subtitle1">🟢 <S text="Added Clauses" /></Typography>
                  {compareMutation.data.added_clauses.map((c, i) => (
                    <Typography key={i} variant="body2">
                      • {c}
                    </Typography>
                  ))}
                </Grid>
                <Grid size={4}>
                  <Typography variant="subtitle1">🔴 <S text="Removed Clauses" /></Typography>
                  {compareMutation.data.removed_clauses.map((c, i) => (
                    <Typography key={i} variant="body2">
                      • {c}
                    </Typography>
                  ))}
                </Grid>
                <Grid size={4}>
                  <Typography variant="subtitle1">🟡 <S text="Modified Clauses" /></Typography>
                  {compareMutation.data.modified_clauses.map((c, i) => (
                    <Typography key={i} variant="body2">
                      • {c}
                    </Typography>
                  ))}
                </Grid>
              </Grid>

              <Typography variant="h6" sx={{ mt: 3 }}>
                ⚠️ <S text="Risk Changes" />
              </Typography>
              <Alert severity="warning" sx={{ mt: 1 }} ref={riskChangesRef}>
                {riskChangesVisible ? <T text={compareMutation.data.risk_changes} /> : compareMutation.data.risk_changes}
              </Alert>

              <Typography variant="h6" sx={{ mt: 3 }}>
                📑 <S text="Detailed Difference Report" />
              </Typography>
              <Typography variant="body2" sx={{ mt: 1, whiteSpace: "pre-wrap" }} ref={differenceReportRef}>
                {differenceReportVisible ? (
                  <T text={compareMutation.data.difference_report} />
                ) : (
                  compareMutation.data.difference_report
                )}
              </Typography>

              <Box sx={{ borderTop: "1px solid", borderColor: "divider", my: 3 }} />

              <SideBySideView
                clausesA={compareMutation.data.clauses_a}
                clausesB={compareMutation.data.clauses_b}
                docAName={compareMutation.data.doc_a_name}
                docBName={compareMutation.data.doc_b_name}
              />
            </Box>
          )}
        </>
      )}
    </>
  );
}
