import { createTheme } from "@mui/material/styles";

// Color tokens ported directly from app.py's injected :root CSS variables
// (--lq-accent, --lq-success, --lq-warning, --lq-danger) — same values, so
// badges/charts/status colors read identically to the Streamlit app.
export const lqColors = {
  accent: "#636EFA",
  accentDark: "#4b4fd1",
  accent2: "#8385f7",
  success: "#00CC96",
  warning: "#FECB52",
  danger: "#EF553B",
};

export const theme = createTheme({
  // Light only — the app should always render on a white background
  // regardless of the OS/browser's dark-mode preference.
  colorSchemes: { light: true },
  palette: {
    primary: { main: lqColors.accent, dark: lqColors.accentDark },
    success: { main: lqColors.success },
    warning: { main: lqColors.warning },
    error: { main: lqColors.danger },
  },
  spacing: 8,
  typography: {
    fontFamily: "'Inter', sans-serif",
    h1: { fontFamily: "'Manrope', sans-serif", fontWeight: 800 },
    h2: { fontFamily: "'Manrope', sans-serif", fontWeight: 800 },
    h3: { fontFamily: "'Manrope', sans-serif", fontWeight: 800 },
    h4: { fontFamily: "'Manrope', sans-serif", fontWeight: 800 },
    h5: { fontFamily: "'Manrope', sans-serif", fontWeight: 800 },
    h6: { fontFamily: "'Manrope', sans-serif", fontWeight: 800 },
  },
  shape: { borderRadius: 10 },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { backgroundColor: "#f7f8fc", color: "#182230" },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { textTransform: "none", fontWeight: 700, borderRadius: 10, boxShadow: "none" },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: { backgroundColor: "#ffffff", borderRadius: 10 },
        notchedOutline: { borderColor: "#dfe3ee" },
      },
    },
    MuiAccordion: {
      styleOverrides: {
        root: {
          border: "1px solid #e6e9f0",
          borderRadius: "10px !important",
          boxShadow: "none",
          overflow: "hidden",
          "&:before": { display: "none" },
          "& + &": { marginTop: 8 },
        },
      },
    },
    MuiAccordionSummary: {
      styleOverrides: {
        root: { minHeight: 48, padding: "0 16px", fontWeight: 700, backgroundColor: "#fbfcff" },
        content: { margin: "12px 0" },
      },
    },
    MuiAccordionDetails: {
      styleOverrides: { root: { padding: "16px" } },
    },
  },
});
