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
  expanded?: boolean
  onToggleExpand?: () => void
  onOpenSource: (item: SourceItem) => void
}

export function CitationChip({
  index,
  source,
  inline,
  expanded,
  onToggleExpand,
  onOpenSource,
}: Props) {
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

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    setHovered(false)
    if (isUnresolved) return
    if (onToggleExpand) {
      onToggleExpand()
    } else {
      onOpenSource(source)
    }
  }

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
        className={`src-chip ${inline ? "inline" : ""} ${isUnresolved ? "unresolved" : ""} ${expanded ? "expanded" : ""}`}
        disabled={isUnresolved}
        onClick={handleClick}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setHovered(false)
          }
        }}
        title={isUnresolved ? t("src.unresolved", "Unresolved source") : source.source}
        aria-label={isUnresolved ? "Unresolved source" : `Source ${index}: ${source.source}`}
        aria-haspopup={!isUnresolved ? "dialog" : undefined}
        aria-expanded={!isUnresolved ? (expanded !== undefined ? expanded : hovered) : undefined}
        aria-describedby={hovered && !isUnresolved ? `popover-citation-${index}` : undefined}
      >
        {inline ? (
          <span className="src-num">{index}</span>
        ) : (
          <>
            <span className="src-num">[{index}]</span>
            <span className="src-name">{isUnresolved ? t("src.unresolved", "Unresolved") : source.source}</span>
            <svg
              className={`src-chev ${expanded ? "expanded" : ""}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </>
        )}
      </button>

      {hovered && !isUnresolved && !expanded && (
        <span id={`popover-citation-${index}`} className="src-popover" role="tooltip">
          <span className="pop-head">
            <span className="pop-idx">[{index}]</span>
            <span className="pop-title">{source.source}</span>
            <span className="pop-badge">{originText}</span>
          </span>
          <span className="pop-excerpt">“{excerptText}”</span>
          <button
            type="button"
            className="pop-foot"
            onClick={(e) => {
              e.stopPropagation()
              onOpenSource(source)
            }}
          >
            {t("src.click_to_open", "Click to inspect source")} ↗
          </button>
        </span>
      )}
    </span>
  )
}
