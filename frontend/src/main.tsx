import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
// Path 1 port — the legacy stylesheets ARE the polish. Cascade order must
// match :8000 exactly: tokens/tailwind scaffold → Deck v4 (static/shell.css,
// linked by every legacy page) → the inline <style> from static/index.html
// (loaded last there, so it wins ties here too). bridge.css dissolves #root.
import "./legacy/deck.css"
import "./legacy/shell.css"
// Inter (self-hosted) must beat deck.css's --sans, which shell.css uses directly
import "./legacy/fonts.css"
import "./legacy/bridge.css"
import "./theme"
import App from "./App"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
