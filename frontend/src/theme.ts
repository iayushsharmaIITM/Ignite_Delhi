// Theme bridge: same localStorage keys as the legacy shell (kestrel.theme),
// applied as data-theme on <html> so both UIs share one setting.
const media = window.matchMedia("(prefers-color-scheme: dark)")

export function resolvedTheme(): "dark" | "light" {
  const t = localStorage.getItem("kestrel.theme") || "system"
  if (t === "dark" || t === "light") return t
  return media.matches ? "dark" : "light"
}

export function applyTheme() {
  document.documentElement.dataset.theme = resolvedTheme()
}

export function setTheme(mode: "system" | "dark" | "light") {
  localStorage.setItem("kestrel.theme", mode)
  applyTheme()
  window.dispatchEvent(new CustomEvent("kestrel:theme", { detail: { theme: mode } }))
}

media.addEventListener("change", () => {
  if ((localStorage.getItem("kestrel.theme") || "system") === "system") {
    applyTheme()
    window.dispatchEvent(new CustomEvent("kestrel:theme", { detail: { theme: "system" } }))
  }
})

applyTheme()
