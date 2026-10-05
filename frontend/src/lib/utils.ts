import { clsx, type ClassValue } from "clsx"
import { useEffect, useRef } from "react"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

/**
 * The keyboard contract every overlay here needs and most here were missing: Escape
 * dismisses, Tab cannot walk out of the dialog into the page behind it, focus lands
 * inside when it opens, and it goes back to what opened the dialog on close.
 *
 * Attach the returned ref to the panel that already carries role="dialog".
 */
export function useDialog<T extends HTMLElement>(open: boolean, onClose: () => void) {
  const ref = useRef<T | null>(null)
  // Every caller writes `onClose={() => setX(false)}`, which is a new function on
  // every render. Depending on it directly would re-run this effect — and re-grab
  // focus — on any unrelated re-render of the parent, so the handler lives behind a
  // ref and the effect keys off `open` alone.
  const close = useRef(onClose)
  useEffect(() => { close.current = onClose }, [onClose])
  useEffect(() => {
    if (!open) return
    const panel = ref.current
    const before = document.activeElement as HTMLElement | null
    const items = () => Array.from(panel?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])
      .filter((el) => !el.hasAttribute("disabled") && el.getClientRects().length > 0)
    // The panel itself, so a screen reader announces the dialog rather than whatever
    // control happens to be first inside it.
    if (panel) (items()[0] ?? panel).focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation()
        close.current()
        return
      }
      if (e.key !== "Tab") return
      const inside = items()
      if (!inside.length) return
      const first = inside[0]
      const last = inside[inside.length - 1]
      const at = document.activeElement
      const outside = !panel?.contains(at)
      if (e.shiftKey && (at === first || outside)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && at === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener("keydown", onKey, true)
    return () => {
      document.removeEventListener("keydown", onKey, true)
      // Only hand focus back if whatever opened the dialog is still there to take it.
      if (before?.isConnected) before.focus()
    }
  }, [open])
  return ref
}
