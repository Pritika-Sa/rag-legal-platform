import { Accordion, AccordionDetails, AccordionSummary, Box, Grid, Stack, Typography } from "@mui/material";
import { useState } from "react";
import type { RiskyClause } from "../../api/riskApi";
import { useInViewOnce } from "../../hooks/useInViewOnce";
import { Badge } from "../common/Badge";
import { HighlightedText } from "../common/HighlightedText";
import { MiniCard } from "../common/MiniCard";
import { S } from "../common/S";
import { T } from "../common/T";
import { RISK_COLORS } from "../../utils/clauseDisplay";
import { riskExplanationBullets } from "../../utils/riskExplanation";
import { useTranslationStore } from "../../store/translationStore";

const PREVIEW_CHARS = 260;

// Direct port of views/risk_analysis.py's flagged-clause card: risk-colored
// accent strip, mini cards, fade-truncated preview with a "View Full
// Clause" toggle for long text, and the plain-English "why risky" bullets.
export function FlaggedClauseCard({ clause }: { clause: RiskyClause }) {
  const [fullTextOpen, setFullTextOpen] = useState(false);
  const translationEnabled = useTranslationStore((s) => s.enabled);
  // "Why This Clause Is Risky" defaults to expanded, so on a document with
  // many flagged clauses every card's risk-explanation bullets would
  // otherwise translate all at once the moment Tamil mode turns on. Only
  // translate once this card has actually scrolled into view.
  const [cardRef, visible] = useInViewOnce<HTMLDivElement>();
  const borderColor = RISK_COLORS[clause.risk_level] ?? "#888888";
  const fullText = clause.text_content || "";
  const isLong = fullText.length > PREVIEW_CHARS;
  const confidenceDisplay: React.ReactNode =
    clause.confidence_score !== null ? (
      <>
        {clause.confidence_score.toFixed(2)} <S text="Confidence" />
      </>
    ) : (
      "—"
    );
  const bullets = riskExplanationBullets(clause.explanation, clause.dimension_breakdown);

  return (
    <Box ref={cardRef} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 3, p: 2, mb: 2 }}>
      <Box sx={{ height: 4, bgcolor: borderColor, borderRadius: 1.5, mb: 1.5 }} />

      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start", mb: 1.5 }}>
        <Typography variant="h6" sx={{ fontSize: "1.05rem" }}>
          ⚠️ {clause.section_name}
        </Typography>
        <Badge label={<S text={`${clause.risk_level.toUpperCase()} RISK`} />} color={borderColor} />
      </Stack>

      <Grid container spacing={1.5} sx={{ mb: 1.5 }}>
        <Grid size={4}>
          <MiniCard label={<S text="Category" />} value={clause.risk_category ?? "—"} icon="🏷" />
        </Grid>
        <Grid size={4}>
          <MiniCard label={<S text="Importance" />} value={clause.importance_category ?? "—"} icon="📈" />
        </Grid>
        <Grid size={4}>
          <MiniCard label={<S text="Confidence" />} value={confidenceDisplay} icon="🎯" />
        </Grid>
      </Grid>

      <Typography
        variant="body2"
        sx={
          isLong && !fullTextOpen
            ? {
                display: "-webkit-box",
                WebkitLineClamp: 4,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }
            : undefined
        }
      >
        {fullText || <S text="No text extracted for this clause." />}
      </Typography>
      {isLong && (
        <Box
          component="button"
          onClick={() => setFullTextOpen(!fullTextOpen)}
          sx={{
            bgcolor: "transparent",
            border: "none",
            color: "primary.main",
            fontWeight: 600,
            fontSize: "0.85rem",
            cursor: "pointer",
            p: 0,
            mt: 0.5,
          }}
        >
          <S text={fullTextOpen ? "Hide Full Clause" : "View Full Clause"} />
        </Box>
      )}

      <Accordion sx={{ mt: 1.5 }} defaultExpanded disableGutters>
        <AccordionSummary>🧠 <S text="Why This Clause Is Risky" /></AccordionSummary>
        <AccordionDetails>
          {bullets.length > 0 ? (
            <Box component="ul" sx={{ pl: 2.5, m: 0 }}>
              {bullets.map((b, i) => (
                <Box component="li" key={i} sx={{ mb: 0.75, fontSize: "0.92rem", lineHeight: 1.5, opacity: 0.9 }}>
                  {/* English keyword-highlighting doesn't apply once the text is Tamil */}
                  {translationEnabled ? (
                    visible ? <T text={b} /> : b
                  ) : (
                    <HighlightedText text={b} />
                  )}
                </Box>
              ))}
            </Box>
          ) : (
            <Typography variant="caption" sx={{ opacity: 0.6 }}>
              <S text="No explanation recorded for this clause yet." />
            </Typography>
          )}
        </AccordionDetails>
      </Accordion>
    </Box>
  );
}
