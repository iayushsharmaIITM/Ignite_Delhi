import { CitationChip, type SourceItem } from "@/components/CitationChip"
import { t } from "@/lib/i18n"

type Props = {
  sources: SourceItem[]
  onOpenSource: (item: SourceItem, allSources?: SourceItem[]) => void
  turnIndex: number
  expandedIndices?: Set<number>
  onToggleIndex?: (index: number) => void
}

export function SourcesSection({
  sources,
  onOpenSource,
}: Props) {
  if (!sources || sources.length === 0) return null

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
      </div>

      <div className="srcs-chips">
        {sources.map((s, si) => (
          <CitationChip
            key={si}
            index={si + 1}
            source={s}
            onOpenSource={() => onOpenSource(s, sources)}
          />
        ))}
      </div>
    </div>
  )
}
