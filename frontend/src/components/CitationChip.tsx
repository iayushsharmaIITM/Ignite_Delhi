import { useState, useRef, useEffect } from "react"
import { t } from "@/lib/i18n"

export type SourceItem = {
  source: string
  excerpt?: string
  version?: string
}

type Props = {
  index: number
  source: SourceItem
  inline?: boolean
  onOpenSource: (item: SourceItem) => void
}

export function CitationChip({ index, source, inline, onOpenSource }: Props) {
  const [hovered, setHovered] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isUnresolved = !source || !source.source

  const handleMouseEnter = () => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setHovered(true), 120)
  }

  const handleMouseLeave = () => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setHovered(false), 100)
  }

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  const originText = source.version
    ? `v.${source.version.slice(0, 8)}`
    : t("src.verified", "Verified source")

  const excerptText = source.excerpt
    ? (source.excerpt.length > 150 ? source.excerpt.slice(0, 150) + "…" : source.excerpt)
    : t("src.view_doc", "Click to inspect cited document")

  return (
    <span
      className={`citation-chip-wrap ${inline ? "inline" : ""}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleMouseEnter}
      onBlur={handleMouseLeave}
    >
      <button
        type="button"
        className={`src-chip ${inline ? "inline" : ""} ${isUnresolved ? "unresolved" : ""}`}
        disabled={isUnresolved}
        onClick={() => {
          if (!isUnresolved) onOpenSource(source)
        }}
        title={isUnresolved ? t("src.unresolved", "Unresolved source") : source.source}
        aria-label={isUnresolved ? "Unresolved source" : `Source ${index}: ${source.source}`}
      >
        {inline ? (
          <span className="src-num">{index}</span>
        ) : (
          <>
            <span className="src-num">[{index}]</span>
            <span className="src-name">{isUnresolved ? t("src.unresolved", "Unresolved") : source.source}</span>
          </>
        )}
      </button>

      {hovered && !isUnresolved && (
        <span className="src-popover" role="tooltip">
          <span className="pop-head">
            <span className="pop-idx">[{index}]</span>
            <span className="pop-title">{source.source}</span>
            <span className="pop-badge">{originText}</span>
          </span>
          <span className="pop-excerpt">“{excerptText}”</span>
          <span className="pop-foot">{t("src.click_to_open", "Click to inspect source")} ↗</span>
        </span>
      )}
    </span>
  )
}
