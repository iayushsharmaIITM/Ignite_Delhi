import React from "react"

export interface LogoProps extends React.SVGProps<SVGSVGElement> {
  size?: number | string
  variant?: "emblem" | "monogram" | "diamond"
  className?: string
}

/**
 * KestrelMark: The core visual brand emblem for Kestrel.
 * - 'emblem': The Aerodynamic Falcon Crest (sharp wings, diamond symmetry, precision angles)
 * - 'monogram': The Stylized K-Wing (modern tech lettermark with soaring wing diagonal)
 * - 'diamond': The Crystalline Faceted Mark (refined evolution of the current diamond)
 */
export function KestrelMark({
  size = 24,
  variant = "emblem",
  className = "",
  ...props
}: LogoProps) {
  const numSize = typeof size === "number" ? size : size

  if (variant === "monogram") {
    return (
      <svg
        width={numSize}
        height={numSize}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`kestrel-mark kestrel-monogram ${className}`}
        aria-label="Kestrel Monogram"
        {...props}
      >
        <defs>
          <linearGradient id="kestrel-mono-grad" x1="4" y1="4" x2="28" y2="28" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#f7ab6d" />
            <stop offset="55%" stopColor="#e87b35" />
            <stop offset="100%" stopColor="#cf6113" />
          </linearGradient>
          <linearGradient id="kestrel-mono-accent" x1="14" y1="4" x2="28" y2="18" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#ffd2a8" />
            <stop offset="100%" stopColor="#e87b35" />
          </linearGradient>
        </defs>
        {/* Vertical stem */}
        <rect x="6" y="5" width="4.5" height="22" rx="1.5" fill="url(#kestrel-mono-grad)" />
        {/* Upper soaring falcon wing feather 1 */}
        <path
          d="M10.5 15.5C14.5 13 20 8.5 26.5 5.5C25.5 8 23 11 19 13.5L25 10C24 12.5 21 15 16.5 17L10.5 15.5Z"
          fill="url(#kestrel-mono-accent)"
        />
        {/* Upper wing feather 2 */}
        <path
          d="M12 16.5C16.5 15.5 22 13.5 25.5 11C23.5 14 19.5 17 15.5 18.5L12 16.5Z"
          fill="url(#kestrel-mono-grad)"
        />
        {/* Lower dynamic landing leg / angle */}
        <path
          d="M12 17.5L21.5 26C22.2 26.6 23.2 27 24.2 27H26C26.5 27 26.8 26.4 26.4 26L16 16.5L12 17.5Z"
          fill="url(#kestrel-mono-grad)"
        />
      </svg>
    )
  }

  if (variant === "diamond") {
    return (
      <svg
        width={numSize}
        height={numSize}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`kestrel-mark kestrel-diamond ${className}`}
        aria-label="Kestrel Faceted Diamond"
        {...props}
      >
        <defs>
          <linearGradient id="kestrel-facet-top" x1="16" y1="3" x2="16" y2="16" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#ffd8b3" />
            <stop offset="100%" stopColor="#f49d54" />
          </linearGradient>
          <linearGradient id="kestrel-facet-left" x1="4" y1="16" x2="16" y2="29" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#e87b35" />
            <stop offset="100%" stopColor="#ba520a" />
          </linearGradient>
          <linearGradient id="kestrel-facet-right" x1="28" y1="16" x2="16" y2="29" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#f49d54" />
            <stop offset="100%" stopColor="#d96f1f" />
          </linearGradient>
        </defs>
        {/* Top facet */}
        <polygon points="16,3 27,14 16,16 5,14" fill="url(#kestrel-facet-top)" />
        {/* Left wing facet */}
        <polygon points="5,14 16,16 16,29 4,16" fill="url(#kestrel-facet-left)" />
        {/* Right wing facet */}
        <polygon points="27,14 28,16 16,29 16,16" fill="url(#kestrel-facet-right)" />
        {/* Center core light point */}
        <polygon points="16,9 19,16 16,23 13,16" fill="#ffffff" opacity="0.3" />
      </svg>
    )
  }

  // Default: Aerodynamic Falcon Emblem
  return (
    <svg
      width={numSize}
      height={numSize}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`kestrel-mark kestrel-emblem ${className}`}
      aria-label="Kestrel Falcon Emblem"
      {...props}
    >
      <defs>
        <linearGradient id="kestrel-grad-main" x1="16" y1="2" x2="16" y2="30" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ffb97d" />
          <stop offset="40%" stopColor="#f49d54" />
          <stop offset="85%" stopColor="#d96f1f" />
          <stop offset="100%" stopColor="#b34e06" />
        </linearGradient>
        <linearGradient id="kestrel-grad-wing-left" x1="3" y1="6" x2="16" y2="20" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ffd4aa" />
          <stop offset="100%" stopColor="#e87b35" />
        </linearGradient>
        <linearGradient id="kestrel-grad-wing-right" x1="29" y1="6" x2="16" y2="20" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#f49d54" />
          <stop offset="100%" stopColor="#ba520a" />
        </linearGradient>
        <linearGradient id="kestrel-grad-core" x1="16" y1="10" x2="16" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#f49d54" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Outer Diamond Shield Outline */}
      <path
        d="M16 2.5L28.5 15L16 29.5L3.5 15L16 2.5Z"
        stroke="url(#kestrel-grad-main)"
        strokeWidth="1.2"
        strokeLinejoin="round"
        opacity="0.35"
      />

      {/* Left Falcon Swept Wing */}
      <path
        d="M16 7L5 12.5L8 16.5L13 14.5L10 19L16 16.5V7Z"
        fill="url(#kestrel-grad-wing-left)"
      />

      {/* Right Falcon Swept Wing */}
      <path
        d="M16 7L27 12.5L24 16.5L19 14.5L22 19L16 16.5V7Z"
        fill="url(#kestrel-grad-wing-right)"
      />

      {/* Falcon Central Body & Beak */}
      <path
        d="M16 5.5L18 9L16 11L14 9L16 5.5Z"
        fill="#ffffff"
        opacity="0.9"
      />
      <path
        d="M16 10L18.5 14L16 26L13.5 14L16 10Z"
        fill="url(#kestrel-grad-main)"
      />

      {/* Aerodynamic Tail Feathers */}
      <polygon points="16,21 14,27 16,29 18,27" fill="#f49d54" />
    </svg>
  )
}

/**
 * Full brand lockup: Icon mark + 'Kestrel' wordmark + optional subtitle
 */
export function KestrelLogo({
  size = 28,
  variant = "emblem",
  showSub = true,
  subText = "Company Brain",
  className = "",
}: {
  size?: number
  variant?: "emblem" | "monogram" | "diamond"
  showSub?: boolean
  subText?: string
  className?: string
}) {
  return (
    <div className={`kestrel-logo-lockup flex items-center gap-2.5 ${className}`}>
      <div className="kestrel-logo-badge flex items-center justify-center rounded-lg bg-gradient-to-br from-panel-2 to-panel border border-line-2 shadow-sm p-1">
        <KestrelMark size={size} variant={variant} />
      </div>
      <div className="flex flex-col leading-tight">
        <span className="text-[14px] font-bold tracking-tight text-foreground font-sans">Kestrel</span>
        {showSub && (
          <span className="text-[10px] font-medium text-muted-foreground tracking-wide">{subText}</span>
        )}
      </div>
    </div>
  )
}
