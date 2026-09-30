import { cn } from "@/lib/cn"

/** The Kestrel diamond mark + wordmark. */
export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <span
        aria-hidden
        className="grid h-8 w-8 flex-none place-items-center rounded-lg bg-accent shadow-[0_0_24px_rgba(232,134,59,0.35)]"
      >
        <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" aria-hidden>
          <rect
            x="4.6"
            y="4.6"
            width="6.8"
            height="6.8"
            rx="1.3"
            transform="rotate(45 8 8)"
            fill="#1a1206"
          />
        </svg>
      </span>
      {!compact && (
        <span className="text-[16.5px] font-semibold tracking-tight text-ink">
          Kestrel
        </span>
      )}
    </span>
  )
}

/** Honest product-stage pill — used in the nav, hero and footer. */
export function StageBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-line-2 bg-panel px-2.5 py-1 text-[11px] font-medium text-ink-2",
        className,
      )}
    >
      <span aria-hidden className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60 motion-reduce:animate-none" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
      </span>
      In development
    </span>
  )
}
