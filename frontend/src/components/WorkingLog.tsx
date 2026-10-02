import { useState, useEffect } from "react"
import { ChevronDown, ChevronRight, Loader2, CheckCircle2, AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"
import { t } from "@/lib/i18n"

export type StepStatus = "done" | "live" | "stopped"

export type Step = {
  label: string
  status: StepStatus
  duration?: number
}

type Props = {
  steps: Step[]
  elapsed: number
  autoCollapse?: boolean
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const rem = Math.round(s % 60)
  return `${m}m ${rem}s`
}

export function WorkingLog({ steps, elapsed, autoCollapse = true }: Props) {
  const [collapsed, setCollapsed] = useState(false)

  // Auto-collapse when all steps are done
  useEffect(() => {
    if (autoCollapse && steps.length > 0 && steps.every((s) => s.status === "done")) {
      setCollapsed(true)
    }
  }, [steps, autoCollapse])

  const hasLive = steps.some((s) => s.status === "live")
  const hasStopped = steps.some((s) => s.status === "stopped")

  return (
    <div className="rounded-lg border border-line bg-panel-2/50">
      {/* Header */}
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        onClick={() => setCollapsed((c) => !c)}
        aria-expanded={!collapsed}
        aria-label={collapsed ? t("working.expand") : t("working.collapse")}
      >
        {collapsed ? (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        )}
        <span className="text-xs font-medium text-muted-foreground">
          {t("working.title")}
        </span>
        {hasLive && (
          <Loader2 className="h-3 w-3 animate-spin text-accent" aria-hidden />
        )}
        {hasStopped && (
          <AlertCircle className="h-3 w-3 text-warn" aria-hidden />
        )}
        <span className="ml-auto text-[11px] text-muted-foreground/70">
          {formatDuration(elapsed)}
        </span>
      </button>

      {/* Steps */}
      {!collapsed && (
        <div className="border-t border-line px-3 py-2">
          <ul className="flex flex-col gap-1.5">
            {steps.map((step, i) => (
              <li key={i} className="flex items-center gap-2 text-xs">
                {/* Status icon */}
                {step.status === "done" && (
                  <CheckCircle2 className="h-3 w-3 shrink-0 text-ok" aria-hidden />
                )}
                {step.status === "live" && (
                  <Loader2 className="h-3 w-3 shrink-0 animate-spin text-accent" aria-hidden />
                )}
                {step.status === "stopped" && (
                  <AlertCircle className="h-3 w-3 shrink-0 text-warn" aria-hidden />
                )}

                {/* Label */}
                <span
                  className={cn(
                    step.status === "done" && "text-muted-foreground",
                    step.status === "live" && "text-foreground",
                    step.status === "stopped" && "text-warn",
                  )}
                >
                  {step.label}
                </span>

                {/* Duration */}
                {step.duration != null && (
                  <span className="ml-auto text-[10px] text-muted-foreground/60">
                    {formatDuration(step.duration)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
