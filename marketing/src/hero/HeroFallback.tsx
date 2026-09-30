/**
 * Static, accessible hero illustration — the same composition as the 3D
 * scene (documents → connections → diamond core → grounded answer), drawn
 * in SVG. This is what renders when WebGL is unavailable, when the user
 * prefers reduced motion, and while the 3D bundle loads.
 */
export function HeroFallback() {
  return (
    <figure className="m-0">
      <svg
        viewBox="0 0 560 470"
        role="img"
        aria-labelledby="hero-fallback-title hero-fallback-desc"
        className="h-auto w-full"
      >
        <title id="hero-fallback-title">
          Scattered documents connect to the Kestrel core and produce a cited answer
        </title>
        <desc id="hero-fallback-desc">
          Illustration: six document cards on the left and right are joined by
          orange lines to a glowing diamond at the centre; an answer card with
          three numbered source references sits beside it.
        </desc>

        <defs>
          <radialGradient id="g-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#e8873a" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#e8873a" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="g-line" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#e8873a" stopOpacity="0.05" />
            <stop offset="50%" stopColor="#e8873a" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#e8873a" stopOpacity="0.05" />
          </linearGradient>
        </defs>

        <circle cx="280" cy="235" r="180" fill="url(#g-glow)" />

        {/* connection lines */}
        {[
          [96, 84], [72, 220], [104, 356], [452, 92], [486, 226], [452, 352],
        ].map(([x, y], i) => (
          <line
            key={i}
            x1={x} y1={y} x2={280} y2={235}
            stroke="url(#g-line)" strokeWidth="1.5"
          />
        ))}

        {/* document cards */}
        {[
          { x: 44, y: 40, t: "MSA · Bluepeak" },
          { x: 18, y: 178, t: "Ticket #4412" },
          { x: 52, y: 314, t: "Meeting · Aug 14" },
          { x: 400, y: 48, t: "SLA credit policy" },
          { x: 436, y: 184, t: "QBR · Aug 28" },
          { x: 400, y: 310, t: "On-call handbook" },
        ].map((c, i) => (
          <g key={i} transform={`translate(${c.x} ${c.y})`}>
            <rect width="112" height="76" rx="9" fill="#212121" stroke="#3a3a3a" />
            <rect x="10" y="12" width="34" height="6" rx="3" fill="#e8873a" opacity="0.85" />
            <text x="10" y="36" fontSize="11.5" fontWeight="600" fill="#f2f0ec" fontFamily="Inter, sans-serif">
              {c.t}
            </text>
            <rect x="10" y="48" width="88" height="5" rx="2.5" fill="#3a3a3a" />
            <rect x="10" y="58" width="62" height="5" rx="2.5" fill="#3a3a3a" />
          </g>
        ))}

        {/* diamond core */}
        <g transform="translate(280 235)">
          <rect
            x="-26" y="-26" width="52" height="52" rx="10"
            transform="rotate(45)"
            fill="#e8873a"
            stroke="#f49d54"
            strokeWidth="1.5"
          />
          <rect
            x="-13" y="-13" width="26" height="26" rx="5"
            transform="rotate(45)"
            fill="#1a1206" opacity="0.9"
          />
        </g>

        {/* answer card */}
        <g transform="translate(176 348)">
          <rect width="216" height="104" rx="12" fill="#212121" stroke="#3a3a3a" />
          <text x="14" y="26" fontSize="11" fontWeight="600" fill="#f2f0ec" fontFamily="Inter, sans-serif">
            Why is the renewal at risk?
          </text>
          <rect x="14" y="38" width="180" height="5" rx="2.5" fill="#3a3a3a" />
          <rect x="14" y="49" width="150" height="5" rx="2.5" fill="#3a3a3a" />
          <rect x="14" y="60" width="168" height="5" rx="2.5" fill="#3a3a3a" />
          {["1", "2", "3"].map((n, i) => (
            <g key={n} transform={`translate(${14 + i * 34} 76)`}>
              <rect width="26" height="16" rx="8" fill="none" stroke="#e8873a" />
              <text x="13" y="11.5" fontSize="9.5" textAnchor="middle" fill="#e8873a" fontFamily="Inter, sans-serif">
                {n}
              </text>
            </g>
          ))}
        </g>
      </svg>
      <figcaption className="mt-3 text-center text-[11.5px] text-muted">
        Illustration — example documents and a simulated answer.
      </figcaption>
    </figure>
  )
}
