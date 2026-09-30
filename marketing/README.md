# Kestrel — public marketing site

A standalone, static landing page for Kestrel Company Brain. Built to deploy
on Cloudflare Pages. It shares the app's brand system (dark charcoal,
`#E8873A` orange, diamond mark) but shares **no code, no runtime and no
secrets** with the application itself — the app under `app.py` / `frontend/`
is untouched by this folder.

Stage honesty rules baked into the page: the product is labeled **In
development**, every shown capability is implemented in the current build,
Slack/email connectors are explicitly **Coming soon**, and the product
walkthrough is a hand-built simulation using the repo's synthetic demo
corpus — clearly labeled as such.

## Build

```bash
cd marketing
npm install
npm run build     # tsc -b && vite build → dist/
npm run dev       # local dev server (http://localhost:5175 by default)
npm run preview   # serve the production build locally
```

Output directory: `marketing/dist/` — pure static files, no server logic.

## Deploy to Cloudflare Pages

1. Push this repo; in the Cloudflare dashboard create a **Pages** project
   connected to it.
2. Build settings:
   - **Framework preset:** Vite (or None)
   - **Build command:** `cd marketing && npm ci && npm run build`
   - **Build output directory:** `marketing/dist`
3. Deploy. `public/_headers` ships long-caching for hashed `/assets/*` plus
   `nosniff` / referrer-policy headers automatically.

No environment variables, no secrets, no build-time API access. The single
external touchpoint is a `mailto:` link defined in `src/contact.ts`.

## Editing the contact address

`src/contact.ts` is the only place an email exists. See
[LAUNCH_BLOCKERS.md](LAUNCH_BLOCKERS.md) before making the site public.

## Structure

```
src/
  components/   Nav, Hero, Demo (simulated app walkthrough), HowItWorks,
                Features, UseCases, Faq, FinalCta, Footer, Logo
  hero/
    Hero3D.tsx      gates WebGL/reduced-motion, lazy-loads the scene
    scene.ts        three.js scene (imperative, single render loop)
    HeroFallback.tsx  static SVG with the same composition (default visual)
  tokens.css    brand tokens (kept in lockstep with ../frontend)
```

## The 3D hero, honestly

- The **static SVG is the default**; the 3D scene only cross-fades in after
  its first real frame, so slow networks never show a blank hero.
- No WebGL or `prefers-reduced-motion` → the SVG stays permanently. Content
  never waits on 3D.
- The render loop pauses when the canvas is offscreen or the tab is hidden;
  pixel ratio is capped lower on modest hardware.
- Pointer parallax is desktop-only and never required to understand the page.
- The scene is an illustration of the product idea (documents → connections →
  cited answer). It does not depict a real backend process, and the caption
  says so.

## Framework choices

React + Vite + Tailwind v4 to match the app frontend's toolchain, but with
plain three.js instead of react-three-fiber: one imperative scene gives full
control over pausing/disposal with one fewer dependency in the bundle.
Evaluated R3F and rejected it for this single-scene use case — see
[LICENSES.md](LICENSES.md) for the dependency inventory.

## Verified

- `npm run build` clean (`tsc -b` strict + Vite).
- Lighthouse (production build, gzip static server): **A11y 100, Perf 98,
  SEO 100, Best practices 100**.
- Screenshots reviewed at 1440×900, 768×1024, 390×844: desktop / tablet /
  mobile hero, product demo, how-it-works, features, FAQ (open + closed),
  mobile menu open.
- Interactions exercised in-browser: mobile menu open/close (Escape closes),
  FAQ `<details>` toggle, anchor navigation, console error walk (zero errors).
