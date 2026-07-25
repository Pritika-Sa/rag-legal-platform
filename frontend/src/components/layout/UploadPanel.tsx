import { Alert, Box, Button, Typography } from "@mui/material";
import { useRef, useState } from "react";
import { extractErrorMessage } from "../../api/authApi";
import { extractAlreadyAnalyzedDocId } from "../../api/documentsApi";
import { useProcessMutation, useUploadMutation } from "../../hooks/useDocuments";
import { useActiveDocumentStore } from "../../store/activeDocumentStore";
import { ALLOWED_UPLOAD_EXTENSIONS, validateUploadFile } from "../../utils/uploadValidation";

// Port of app.py's sidebar upload block: st.file_uploader writes the file to
// disk immediately (Phase 3), then the separate "Process Document" button
// runs agents.orchestrator.run_orchestration (Phase 4) — same two-step flow,
// same three outcomes (already-analyzed / failed / success), same summary
// banner text.
export function UploadPanel() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [clientError, setClientError] = useState<string | null>(null);
  const uploadMutation = useUploadMutation();
  const processMutation = useProcessMutation();
  const { setActiveDocument } = useActiveDocumentStore();

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    uploadMutation.reset();
    processMutation.reset();
    setClientError(null);
    if (!file) return;

    const validationError = validateUploadFile(file);
    if (validationError) {
      setClientError(validationError);
      e.target.value = "";
      return;
    }

    uploadMutation.mutate(file);
  };

  const handleProcess = () => {
    if (!uploadMutation.data) return;
    const { file_path, name } = uploadMutation.data;
    processMutation.mutate(
      { filePath: file_path, name },
      {
        onSuccess: (result) => {
          setActiveDocument(result.doc_id, name);
        },
        onError: (error) => {
          const alreadyAnalyzedDocId = extractAlreadyAnalyzedDocId(error);
          if (alreadyAnalyzedDocId !== null) {
            setActiveDocument(alreadyAnalyzedDocId, name);
          }
        },
      },
    );
  };

  const alreadyAnalyzedDocId = processMutation.isError
    ? extractAlreadyAnalyzedDocId(processMutation.error)
    : null;

  return (
    <Box sx={{ mb: 2 }}>
      <input
        ref={inputRef}
        type="file"
        accept={ALLOWED_UPLOAD_EXTENSIONS.map((ext) => `.${ext}`).join(",")}
        onChange={handleFileChange}
        style={{ display: "none" }}
      />
      <Button
        variant="outlined"
        fullWidth
        onClick={() => inputRef.current?.click()}
        loading={uploadMutation.isPending}
      >
        📤 Upload a document
      </Button>
      <Typography sx={{ fontSize: "0.7rem", opacity: 0.55, mt: 0.5 }}>
        PDF, Word, or text contracts. Images are OCR&apos;d automatically before analysis.
      </Typography>

      {clientError && (
        <Alert severity="error" sx={{ fontSize: "0.78rem", mt: 1 }}>
          {clientError}
        </Alert>
      )}
      {uploadMutation.isError && (
        <Alert severity="error" sx={{ fontSize: "0.78rem", mt: 1 }}>
          {extractErrorMessage(uploadMutation.error, "Upload failed.")}
        </Alert>
      )}

      {uploadMutation.isSuccess && !processMutation.isSuccess && (
        <Box sx={{ mt: 1 }}>
          {!processMutation.isError && (
            <Alert severity="success" sx={{ fontSize: "0.78rem" }}>
              &apos;{uploadMutation.data.name}&apos; uploaded.
            </Alert>
          )}

          {alreadyAnalyzedDocId !== null && (
            <Alert severity="warning" sx={{ fontSize: "0.78rem", mt: 1 }}>
              This document has already been analyzed.
            </Alert>
          )}
          {processMutation.isError && alreadyAnalyzedDocId === null && (
            <Alert severity="error" sx={{ fontSize: "0.78rem", mt: 1 }}>
              {extractErrorMessage(processMutation.error, "An error occurred during analysis.")}
            </Alert>
          )}

          <Button
            variant="contained"
            fullWidth
            sx={{ mt: 1 }}
            onClick={handleProcess}
            loading={processMutation.isPending}
            disabled={alreadyAnalyzedDocId !== null}
          >
            🚀 Process Document
          </Button>
          {processMutation.isPending && (
            <Typography sx={{ fontSize: "0.7rem", opacity: 0.6, mt: 0.5, textAlign: "center" }}>
              Processing Status: running multi-agent analysis…
            </Typography>
          )}
        </Box>
      )}

      {processMutation.isSuccess && (
        <Box sx={{ mt: 1 }}>
          <Alert severity="success" sx={{ fontSize: "0.78rem" }}>
            🎉 &apos;{uploadMutation.data?.name}&apos; processed — {processMutation.data.clause_count} clauses found.
          </Alert>
          <Typography sx={{ fontSize: "0.72rem", opacity: 0.65, mt: 0.5 }}>
            Risk {processMutation.data.document_risk_score}/100
          </Typography>
          {processMutation.data.parsing_quality_warning && (
            <Alert severity="warning" sx={{ fontSize: "0.75rem", mt: 0.5 }}>
              ⚠️ {processMutation.data.parsing_quality_warning}
            </Alert>
          )}
        </Box>
      )}
    </Box>
  );
}
