import { useState } from "react"
import { CitationChip, type SourceItem } from "@/components/CitationChip"
import { t } from "@/lib/i18n"

type Props = {
  sources: SourceItem[]
  onOpenSource: (item: SourceItem) => void
  turnIndex: number
  expandedIndices?: Set<number>
  onToggleIndex?: (index: number) => void
}

export function SourcesSection({
  sources,
  onOpenSource,
  turnIndex,
  expandedIndices: externalExpanded,
  onToggleIndex: externalToggle,
}: Props) {
  const [internalExpanded, setInternalExpanded] = useState<Set<number>>(new Set())

  const isControlled = externalExpanded !== undefined
  const activeExpanded = isControlled ? externalExpanded : internalExpanded

  const handleToggle = (index: number) => {
    if (externalToggle) {
      externalToggle(index)
    } else {
      setInternalExpanded((prev) => {
        const next = new Set(prev)
        if (next.has(index)) {
          next.delete(index)
        } else {
          next.add(index)
        }
        return next
      })
    }
  }

  const handleToggleAll = () => {
    const allCount = sources.length
    const areAllExpanded = activeExpanded.size === allCount
    if (isControlled && externalToggle) {
      for (let i = 0; i < allCount; i++) {
        if (areAllExpanded ? activeExpanded.has(i) : !activeExpanded.has(i)) {
          externalToggle(i)
        }
      }
    } else {
      if (areAllExpanded) {
        setInternalExpanded(new Set())
      } else {
        setInternalExpanded(new Set(sources.map((_, i) => i)))
      }
    }
  }

  if (!sources || sources.length === 0) return null

  const allExpanded = activeExpanded.size === sources.length

  return (
    <div className="srcs" role="region" aria-label="Cited sources">
      <div className="srcs-header">
        <div className="srcs-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          <span>{t("src.sources_label", "Sources")}</span>
          <span className="srcs-count">{sources.length}</span>
        </div>
        {sources.length > 1 && (
          <button
            type="button"
            className="srcs-toggle-all"
            onClick={handleToggleAll}
          >
            {allExpanded ? t("src.collapse_all", "Collapse all") : t("src.expand_all", "Expand all")}
          </button>
        )}
      </div>

      <div className="srcs-chips">
        {sources.map((s, si) => (
          <CitationChip
            key={si}
            index={si + 1}
            source={s}
            expanded={activeExpanded.has(si)}
            onToggleExpand={() => handleToggle(si)}
            onOpenSource={onOpenSource}
          />
        ))}
      </div>

      {activeExpanded.size > 0 && (
        <div className="srcs-tray" role="region" aria-label="Expanded source excerpts">
          {sources.map((s, si) => {
            if (!activeExpanded.has(si)) return null
            const originText = s.version
              ? `v.${s.version.slice(0, 8)}`
              : t("src.verified", "Verified source")
            const isUnresolved = !s || !s.source

            return (
              <div
                key={si}
                className="src-expanded-card"
                id={`src-expanded-${turnIndex}-${si}`}
              >
                <div className="src-card-head">
                  <div className="src-card-meta">
                    <span className="src-num">[{si + 1}]</span>
                    <span className="src-card-title" title={s.source}>
                      {isUnresolved ? t("src.unresolved", "Unresolved") : s.source}
                    </span>
                    <span className="src-card-badge">{originText}</span>
                  </div>
                  <div className="src-card-actions">
                    {!isUnresolved && (
                      <button
                        type="button"
                        className="src-open-full"
                        title={t("src.open_full", "Open full document")}
                        onClick={() => onOpenSource(s)}
                      >
                        <span>{t("src.open_full_doc", "Open document")}</span>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                          <polyline points="15 3 21 3 21 9" />
                          <line x1="10" y1="14" x2="21" y2="3" />
                        </svg>
                      </button>
                    )}
                    <button
                      type="button"
                      className="src-card-close"
                      aria-label={t("src.collapse", "Collapse")}
                      title={t("src.collapse", "Collapse")}
                      onClick={() => handleToggle(si)}
                    >
                      ×
                    </button>
                  </div>
                </div>
                <div className="src-card-body">
                  <div className="src-card-quote">
                    “{s.excerpt || t("src.view_doc", "Click to inspect cited document")}”
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
