# Launch blockers — read before making the site public

The site is deployable as-is, but these items are deliberately NOT faked in
the page. Each needs a human decision.

## 1. Contact email needs explicit confirmation

`src/contact.ts` currently uses `smartyayush333@gmail.com`, taken from the
repo's git identity — the only contact address that exists anywhere in this
project. Publishing a personal Gmail on a public site is a decision only
Ayush can make. **Confirm it, or replace it with a domain address** (e.g.
something on the eventual kestrel domain) — one line in one file.

## 2. No legal pages (privacy policy / terms)

There are none in the repo, and none were fabricated. For a site that only
describes a product and offers a mailto link this is tolerable at private-
beta scale, but before any public launch that collects emails or ships the
product, privacy policy and terms must exist — especially because the
product itself sends document content to third-party AI providers.

## 3. No real contact form endpoint

The primary CTA is `mailto:` (works everywhere, zero backend). When volume
justifies it, wire a real form (Cloudflare Pages Functions or a form
provider) — until then there is deliberately **no fake waitlist success
message** anywhere.

## 4. Stage claims are time-boxed

The page says "In development" and marks Slack/email connectors "Coming
soon". When those connectors ship or the product enters a real beta, update:
- the `StageBadge` label (`src/components/Logo.tsx`),
- the Features "Coming soon" strip (`src/components/Features.tsx`),
- the FAQ account/integrations answers (`src/components/Faq.tsx`).

## 5. Sign-in / sign-up intentionally absent

Per the phase brief, the marketing site has no auth buttons — the app's
Clerk integration stays separate. When the app has production deployment
settings, the nav gains "Sign in" pointing at the app domain, with the
branded Clerk appearance already prepared in the app — since 2026-10-04 that is
`appearanceProps()` in `frontend/src/components/Animations.tsx`, which themes the
sign-in from the same tokens as the rest of the product. (This bullet used to name
`static/auth.js`; that file was deleted with the rest of the legacy UI, so the
claim would have sent someone looking for a surface that no longer exists.)
No second password database exists or will exist.

## 6. Social cards need a final domain

`og:image` / `twitter:image` use relative `./og.png`, which most crawlers
resolve fine once deployed, but absolute URLs are more reliable. Set the
final production domain in `index.html` (and consider a dedicated 1200×630
design rather than the live-capture currently shipped).

## What was verified before writing this list

- Build clean; Lighthouse A11y 100 / Perf 98 / SEO 100 / BP 100.
- Browser-tested at 1440×900, 768×1024, 390×844; mobile menu, FAQ accordion,
  anchors, console-error walk all clean.
- The 3D hero degrades to a static SVG on WebGL failure / reduced motion;
  rendering pauses offscreen and on hidden tabs.
