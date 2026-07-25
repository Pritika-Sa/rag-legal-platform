import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import { useState } from "react";
import type { ClauseWithIntelligence } from "../../api/clausesApi";
import { useSimplifyMutation } from "../../hooks/useClauses";
import {
  COMPLIANCE_COLORS,
  IMPACT_LEVEL_COLORS,
  IMPORTANCE_COLORS,
  RISK_COLORS,
  complianceStatus,
  confidenceTier,
  impactLevelLabel,
  impactLevelScore,
} from "../../utils/clauseDisplay";
import { Badge } from "../common/Badge";
import { MiniCard } from "../common/MiniCard";
import { PlotlyChart } from "../common/PlotlyChart";

interface ClauseCardProps {
  docId: number;
  clause: ClauseWithIntelligence;
}

// Direct port of views/clause_analysis.py's per-clause card: same mini
// cards, same details table, same three lazy sections (original text,
// AI simplification, impact analysis).
export function ClauseCard({ docId, clause }: ClauseCardProps) {
  const [textOpen, setTextOpen] = useState(false);
  const [simplifyOpen, setSimplifyOpen] = useState(false);
  const [impactOpen, setImpactOpen] = useState(false);
  const simplifyMutation = useSimplifyMutation(docId);

  const riskLevel = clause.risk_level || "None";
  const complianceLabel = complianceStatus(clause.compliance_impact);
  const impactScore = impactLevelScore(
    clause.legal_impact,
    clause.financial_impact,
    clause.business_impact,
    clause.compliance_impact,
  );
  const impactLabel = impactLevelLabel(impactScore);

  const handleSimplifyToggle = () => {
    const opening = !simplifyOpen;
    setSimplifyOpen(opening);
    if (opening && !simplifyMutation.data && !simplifyMutation.isPending) {
      simplifyMutation.mutate(clause.id);
    }
  };

  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 3, p: 2, mb: 2 }}>
      <Grid container spacing={1.5} sx={{ mb: 1.5 }}>
        <Grid size={{ xs: 12, sm: 5 }}>
          <MiniCard label="Clause Title" value={clause.section_name} icon="📌" />
        </Grid>
        <Grid size={{ xs: 6, sm: 3.5 }}>
          <MiniCard label="Category" value={clause.risk_category ?? "—"} icon="🏷" />
        </Grid>
        <Grid size={{ xs: 6, sm: 3.5 }}>
          <MiniCard label="Type" value={clause.classification ?? "Unclassified"} icon="📑" />
        </Grid>
      </Grid>

      <Box component="table" sx={{ width: "100%", borderCollapse: "collapse", fontSize: "0.92rem", mb: 1.5 }}>
        <tbody>
          <ClauseTableRow field="Clause Classification" value={confidenceTier(clause.confidence_score)} />
          <ClauseTableRow
            field="Importance Level"
            value={<Badge label={clause.importance_category.toUpperCase()} color={IMPORTANCE_COLORS[clause.importance_category] ?? "#888888"} />}
          />
          <ClauseTableRow
            field="Risk Level"
            value={<Badge label={`${riskLevel.toUpperCase()} RISK`} color={RISK_COLORS[riskLevel] ?? "#888888"} />}
          />
          <ClauseTableRow
            field="Compliance Status"
            value={<Badge label={complianceLabel.toUpperCase()} color={COMPLIANCE_COLORS[complianceLabel] ?? "#888888"} />}
          />
        </tbody>
      </Box>

      <Accordion expanded={textOpen} onChange={() => setTextOpen(!textOpen)} disableGutters>
        <AccordionSummary>{textOpen ? "▼" : "▶"}&nbsp;&nbsp;View Original Clause Text</AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2">{clause.text_content || "No text extracted for this clause."}</Typography>
        </AccordionDetails>
      </Accordion>

      <Accordion expanded={simplifyOpen} onChange={handleSimplifyToggle} disableGutters>
        <AccordionSummary>{simplifyOpen ? "▼" : "▶"}&nbsp;&nbsp;Simplify Clause</AccordionSummary>
        <AccordionDetails>
          {simplifyMutation.isPending && (
            <Typography variant="body2" sx={{ opacity: 0.7 }}>
              Agent 7 is translating legalese to plain English...
            </Typography>
          )}
          {simplifyMutation.isError && !clause.simplification && (
            <Alert severity="error">Simplification failed.</Alert>
          )}
          {simplifyMutation.data ? (
            <SimplifyResult
              result={simplifyMutation.data}
              onRegenerate={() => simplifyMutation.mutate(clause.id)}
              regenerating={simplifyMutation.isPending}
            />
          ) : (
            simplifyMutation.isError &&
            clause.simplification && (
              <>
                <Typography variant="caption" sx={{ opacity: 0.6 }}>
                  AI generation failed — showing the previously saved plain-English redraft instead.
                </Typography>
                <Typography variant="body2" sx={{ mt: 1 }}>
                  {clause.simplification}
                </Typography>
              </>
            )
          )}
        </AccordionDetails>
      </Accordion>

      <Accordion expanded={impactOpen} onChange={() => setImpactOpen(!impactOpen)} disableGutters>
        <AccordionSummary>📊 Impact Analysis</AccordionSummary>
        <AccordionDetails>
          {!clause.impact_chart || impactScore === null ? (
            <Typography variant="caption" sx={{ opacity: 0.6 }}>
              Impact scoring unavailable for this clause.
            </Typography>
          ) : (
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 5.5 }}>
                <PlotlyChart figure={clause.impact_chart} height={260} />
              </Grid>
              <Grid size={{ xs: 12, md: 6.5 }}>
                <Stack spacing={0.5}>
                  <Typography variant="body2">
                    <strong>Impact Level:</strong>{" "}
                    {impactLabel && <Badge label={impactLabel.toUpperCase()} color={IMPACT_LEVEL_COLORS[impactLabel] ?? "#888888"} />}
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.65 }}>
                    Overall severity of this clause&apos;s impact across legal, financial, business, and compliance dimensions.
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>Business Impact:</strong> {clause.business_impact}/100
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.65 }}>
                    How significantly this clause could affect business operations, SLAs, or deliverables.
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>Legal Impact:</strong> {clause.legal_impact}/100
                  </Typography>
                  <Typography variant="caption" sx={{ opacity: 0.65 }}>
                    How significantly this clause could affect legal exposure or enforceability.
                  </Typography>
                </Stack>
              </Grid>
            </Grid>
          )}
        </AccordionDetails>
      </Accordion>
    </Box>
  );
}

function ClauseTableRow({ field, value }: { field: string; value: React.ReactNode }) {
  return (
    <Box component="tr" sx={{ borderBottom: "1px solid", borderColor: "divider" }}>
      <Box component="td" sx={{ py: 1.1, px: 1.75, fontWeight: 600, opacity: 0.65, whiteSpace: "nowrap", width: 200 }}>
        {field}
      </Box>
      <Box component="td" sx={{ py: 1.1, px: 1.75 }}>
        {value}
      </Box>
    </Box>
  );
}

function SimplifyResult({
  result,
  onRegenerate,
  regenerating,
}: {
  result: { simplified_clause: string; easy_summary: string; rights: string; obligations: string; hidden_risks: string; ai_recommendation: string };
  onRegenerate: () => void;
  regenerating: boolean;
}) {
  return (
    <Stack spacing={1.5}>
      <Box>
        <Typography variant="subtitle2">💬 Plain English Explanation</Typography>
        <Typography variant="body2">{result.simplified_clause}</Typography>
      </Box>
      <Box>
        <Typography variant="subtitle2">📝 Easy Summary</Typography>
        <Typography variant="body2">{result.easy_summary}</Typography>
      </Box>
      <Grid container spacing={2}>
        <Grid size={6}>
          <Typography variant="subtitle2">✅ Rights</Typography>
          <Typography variant="body2">{result.rights}</Typography>
        </Grid>
        <Grid size={6}>
          <Typography variant="subtitle2">📌 Obligations</Typography>
          <Typography variant="body2">{result.obligations}</Typography>
        </Grid>
      </Grid>
      <Alert severity="warning" sx={{ fontSize: "0.85rem" }}>
        <strong>⚠️ Hidden Risks</strong>
        <br />
        {result.hidden_risks}
      </Alert>
      <Alert severity="success" sx={{ fontSize: "0.85rem" }}>
        <strong>💡 AI Recommendation</strong>
        <br />
        {result.ai_recommendation}
      </Alert>
      <Button size="small" onClick={onRegenerate} loading={regenerating} sx={{ alignSelf: "flex-start" }}>
        🔄 Regenerate with AI (Agent 7)
      </Button>
    </Stack>
  );
}
