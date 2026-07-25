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
  colorSchemes: { light: true, dark: true },
  palette: {
    primary: { main: lqColors.accent, dark: lqColors.accentDark },
    success: { main: lqColors.success },
    warning: { main: lqColors.warning },
    error: { main: lqColors.danger },
  },
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
    MuiButton: {
      styleOverrides: {
        root: { textTransform: "none", fontWeight: 600 },
      },
    },
  },
});
