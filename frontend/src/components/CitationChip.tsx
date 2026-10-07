import { useState, useRef, useEffect } from "react"
import { t } from "@/lib/i18n"

export type SourceItem = {
  source: string
  excerpt?: string
  version?: string
  text?: string
  is_attachment?: boolean
}

type Props = {
  index: number
  source: SourceItem
  inline?: boolean
  onOpenSource: (item: SourceItem) => void
}

export function CitationChip({
  index,
  source,
  inline,
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

  const originText = source.is_attachment
    ? t("src.attachment", "Attached screenshot / file")
    : source.version
    ? `v.${source.version.slice(0, 8)}`
    : t("src.verified", "Verified source")

  const excerptText = source.excerpt
    ? (source.excerpt.length > 150 ? source.excerpt.slice(0, 150) + "…" : source.excerpt)
    : t("src.view_doc", "Click to inspect cited document")

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    setHovered(false)
    if (isUnresolved) return
    onOpenSource(source)
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
        className={`src-chip ${inline ? "inline" : ""} ${isUnresolved ? "unresolved" : ""}`}
        disabled={isUnresolved}
        onClick={handleClick}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setHovered(false)
          }
        }}
        title={isUnresolved ? t("src.unresolved", "Unresolved source") : `${source.source} — Click to open source`}
        aria-label={isUnresolved ? "Unresolved source" : `Source ${index}: ${source.source}. Click to open document`}
        aria-haspopup={!isUnresolved ? "dialog" : undefined}
      >
        {inline ? (
          <span className="src-num">{index}</span>
        ) : (
          <>
            <span className="src-num">[{index}]</span>
            <span className="src-name">{isUnresolved ? t("src.unresolved", "Unresolved") : source.source}</span>
            <svg
              className="src-open-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </>
        )}
      </button>

      {hovered && !isUnresolved && (
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
              setHovered(false)
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
