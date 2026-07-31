import { Accordion, AccordionDetails, AccordionSummary, Alert, Grid, Typography } from "@mui/material";
import type { ClauseForComparison } from "../../api/comparisonApi";
import { S } from "../common/S";

interface SideBySideViewProps {
  clausesA: ClauseForComparison[];
  clausesB: ClauseForComparison[];
  docAName: string;
  docBName: string;
}

// Port of views/comparison.py's "Side-by-Side Reference" section: groups
// each document's clauses by classification (last-one-wins per type, same
// as the original's plain dict comprehension), one expander per type shared
// across both documents.
export function SideBySideView({ clausesA, clausesB, docAName, docBName }: SideBySideViewProps) {
  const dictA: Record<string, string> = {};
  for (const c of clausesA) if (c.classification) dictA[c.classification] = c.text_content;
  const dictB: Record<string, string> = {};
  for (const c of clausesB) if (c.classification) dictB[c.classification] = c.text_content;

  const allClasses = Array.from(new Set([...Object.keys(dictA), ...Object.keys(dictB)])).sort();

  return (
    <>
      <Typography variant="h6" sx={{ mb: 2 }}>
        📖 <S text="Side-by-Side Reference" />
      </Typography>
      {allClasses.map((cType) => {
        const textA = dictA[cType];
        const textB = dictB[cType];
        return (
          <Accordion key={cType} disableGutters sx={{ mb: 1 }}>
            <AccordionSummary>
              <S text="Type:" /> {cType}
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid size={6}>
                  <Typography variant="subtitle2">
                    <S text="Document 1" /> ({docAName}):
                  </Typography>
                  <Alert severity="info" sx={{ mt: 1 }}>
                    {textA ?? <S text="*(Clause not present in Agreement A)*" />}
                  </Alert>
                </Grid>
                <Grid size={6}>
                  <Typography variant="subtitle2">
                    <S text="Document 2" /> ({docBName}):
                  </Typography>
                  <Alert severity="info" sx={{ mt: 1 }}>
                    {textB ?? <S text="*(Clause not present in Agreement B)*" />}
                  </Alert>
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>
        );
      })}
    </>
  );
}
