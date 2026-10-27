import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { laadCatalogus } from "./catalogus";
import "./index.css";

// Op de achtergrond ophalen zodra de app opent (niet op de aanmeldpagina's, daar is er nog geen sessie).
if (!["/aanmelden", "/afgemeld", "/fout"].includes(window.location.pathname)) laadCatalogus().catch(() => {});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
