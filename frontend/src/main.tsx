import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App.tsx"
import "./index.css"
import { applyDocumentLang, initialLang } from "@/lib/i18n"

// Set before the first render, so a returning Arabic reader never sees an LTR frame flash.
applyDocumentLang(initialLang())

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
