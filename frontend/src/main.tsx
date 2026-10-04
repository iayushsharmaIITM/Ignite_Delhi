import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
// The design system. These four files ARE the product's visual language — they
// began as the legacy shell's stylesheets and are where its polish lives — so
// they were renamed out of `legacy/`, a directory name that repeatedly read as
// dead code to everyone from a first pass to a review agent.
//
// Cascade order is load-bearing and must not be reordered: tokens/tailwind
// scaffold → deck.css (the palette and shell) → shell.css → the typography
// override (fonts.css, which has to beat deck.css's --sans) → bridge.css, which
// dissolves #root so the shell lays out from body exactly as it did when the
// markup was hand-written.
import "./design/deck.css"
import "./design/shell.css"
import "./design/fonts.css"
import "./design/bridge.css"
import "./theme"
import App from "./App"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
