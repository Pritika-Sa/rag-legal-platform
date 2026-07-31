import { Alert, Box, Button, CircularProgress, Stack, Typography } from "@mui/material";
import { ContradictionCard } from "../components/contradiction/ContradictionCard";
import { PageHeader } from "../components/common/PageHeader";
import { S } from "../components/common/S";
import { useContradictionsQuery, useReanalyzeContradictionsMutation } from "../hooks/useContradictions";
import { useActiveDocumentStore } from "../store/activeDocumentStore";

// Direct port of views/contradiction.py::render(). The one-time AI pass on
// first visit and the backfill-forces-redo logic both happen server-side
// (api/routers/contradictions.py), so this page just renders whatever GET
// returns and offers the same "Re-analyze with AI" button.
export function ContradictionPage() {
  const { activeDocId, activeDocName } = useActiveDocumentStore();
  const contradictionsQuery = useContradictionsQuery(activeDocId);
  const reanalyzeMutation = useReanalyzeContradictionsMutation(activeDocId ?? -1);

  const contradictions = reanalyzeMutation.data ?? contradictionsQuery.data ?? [];

  return (
    <>
      <PageHeader
        icon="⚖️"
        title="Contradiction & Inconsistency Finder"
        subtitle="Identifies conflicting statements, inconsistent obligations, and contradictory terms within the document."
        docName={activeDocName}
      />

      {!activeDocId && (
        <Alert severity="warning"><S text="Please select an active document in the sidebar to review contradictions." /></Alert>
      )}

      {activeDocId && contradictionsQuery.isLoading && (
        <Box sx={{ textAlign: "center", py: 6 }}>
          <CircularProgress />
          <Typography variant="body2" sx={{ mt: 2, opacity: 0.7, maxWidth: 480, mx: "auto" }}>
            <S text="Finding contradictions and inconsistencies in this document… This may take a few seconds, depending on the document's length and complexity." />
          </Typography>
        </Box>
      )}

      {activeDocId && contradictionsQuery.isError && (
        <Alert severity="error"><S text="Failed to load contradictions for this document." /></Alert>
      )}

      {activeDocId && contradictionsQuery.isSuccess && (
        <>
          <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 2 }}>
            {contradictions.length > 0 ? (
              <Typography variant="h6">
                <S text="Found" /> <strong>{contradictions.length}</strong> <S text="internal conflicts:" />
              </Typography>
            ) : (
              <Alert severity="success" sx={{ flexGrow: 1, mr: 2 }}>
                ✅ <S text="No conflicting clauses or internal contradictions were detected in this agreement!" />
              </Alert>
            )}
            <Button
              variant="outlined"
              onClick={() => reanalyzeMutation.mutate()}
              loading={reanalyzeMutation.isPending}
            >
              🔄 <S text="Re-analyze with AI" />
            </Button>
          </Stack>

          {reanalyzeMutation.isError && <Alert severity="error" sx={{ mb: 2 }}><S text="Failed to re-analyze this document." /></Alert>}

          {contradictions.map((c) => (
            <ContradictionCard key={c.id} contradiction={c} />
          ))}
        </>
      )}
    </>
  );
}
