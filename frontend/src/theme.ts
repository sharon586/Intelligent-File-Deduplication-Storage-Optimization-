import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#2f5bea" },
    secondary: { main: "#00897b" },
    background: { default: "#f4f6fb" },
  },
  shape: { borderRadius: 10 },
  typography: { fontFamily: '"Inter", "Roboto", "Segoe UI", Arial, sans-serif' },
});
