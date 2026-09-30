# Dependency and license inventory — marketing site

Everything below is free and open source. "Free" is not "unrestricted" —
licenses are recorded per package with what they require.

## Runtime dependencies

| Package | Version | License | Notes / obligations |
|---|---|---|---|
| react | 19.2.x | MIT | Keep the copyright notice in the bundle (Vite retains LICENSE comments by default). |
| react-dom | 19.2.x | MIT | Same as react. |
| three | 0.181.x | MIT | Copyright notice retained in the lazy scene chunk. |
| lucide-react | 1.49.x | ISC | Icon set; notice retained. |
| @fontsource-variable/inter | 5.2.x | SIL OFL 1.1 | The Inter typeface. OFL allows self-hosting and bundling; it forbids selling the font standalone and using reserved names for derivatives. Bundling the woff2 in a website build is standard compliant use. |

## Dev dependencies

| Package | License |
|---|---|
| vite | MIT |
| @vitejs/plugin-react | MIT |
| typescript | Apache-2.0 |
| tailwindcss, @tailwindcss/vite | MIT |
| @types/react, @types/react-dom, @types/three | MIT |

## Assets

- Logo (diamond mark): original, drawn in this repo (SVG) — no third-party rights.
- Product-walkthrough mock: hand-built HTML/CSS using the repo's own synthetic
  demo corpus (`corpus/01–10` fixtures) — no real user data, no screenshots of
  real customers.
- `public/og.png`: generated screenshot of this site's own hero.
- No stock imagery, no paid models, no proprietary embeds, no analytics
  scripts, no third-party trackers.

## Cost statement (kept separate, as requested)

- **This site's libraries:** $0 (all MIT/ISC/OFL).
- **Hosting:** Cloudflare Pages free tier serves this static site at no cost
  within generous limits; a custom domain costs whatever the registrar
  charges.
- **Auth service (future phase):** Clerk has its own pricing — not used by
  this site and not incurred by it.
- **AI service (the product):** the app's LLM/OCR providers bill separately
  and are unrelated to this marketing build.
