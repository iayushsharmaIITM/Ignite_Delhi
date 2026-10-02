import { Sparkles } from "lucide-react"
import { t } from "@/lib/i18n"

type Props = {
  suggestions: string[]
  onSelect: (s: string) => void
}

export function SuggestionChips({ suggestions, onSelect }: Props) {
  if (suggestions.length === 0) return null

  return (
    <div className="mt-4">
      <div className="mb-2 flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
        <Sparkles className="h-3 w-3" aria-hidden />
        {t("suggestions.title")}
      </div>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onSelect(s)}
            className="rounded-full border border-line bg-panel px-3.5 py-1.5 text-[12.5px] text-foreground/80 transition-all duration-150 ease-out hover:border-accent/60 hover:bg-accent-dim hover:text-accent"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
