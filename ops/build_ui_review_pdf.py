"""Build docs/ui-review/UI_REVIEW_PACKAGE.pdf — one file: cover + theme + all screenshots."""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENS = os.path.join(HERE, "docs", "ui-review", "screens")
BG, PANEL, ACCENT, INK, MUTED = (20,20,20), (33,33,33), (232,134,59), (242,240,236), (168,164,157)
PAGE_W, PAGE_H = 2000, 1414
F = "/System/Library/Fonts/Supplemental/Arial.ttf"
def font(sz): return ImageFont.truetype(F, sz)

def text_page(draw, title, sub, body):
    draw.rectangle([0,0,PAGE_W,8], fill=ACCENT)
    draw.text((90, 90), "Kestrel UI Review", font=font(40), fill=MUTED)
    draw.text((90, 160), title, font=font(64), fill=INK)
    y = 280
    for line in sub:
        draw.text((90, y), line, font=font(38), fill=(214,210,202)); y += 60
    y += 30
    for line in body:
        draw.text((90, y), line, font=font(30), fill=MUTED); y += 46

def img_page(page, img, num, total, caption, note=""):
    draw = ImageDraw.Draw(page)
    draw.rectangle([0,0,PAGE_W,8], fill=ACCENT)
    draw.text((90, 55), caption, font=font(44), fill=INK)
    if note: draw.text((90, 115), note, font=font(28), fill=MUTED)
    draw.text((PAGE_W-320, 55), f"{num} / {total}", font=font(34), fill=MUTED)
    im = Image.open(img).convert("RGB")
    maxw, maxh = PAGE_W-180, PAGE_H-320
    scale = min(maxw/im.width, maxh/im.height)
    w, h = int(im.width*scale), int(im.height*scale)
    im = im.resize((w, h), Image.LANCZOS)
    x, y = (PAGE_W-w)//2, 190 + (maxh-h)//2
    draw.rectangle([x-4, y-4, x+w+4, y+h+4], outline=(58,58,58), width=3)
    page.paste(im, (x, y))
    draw.rectangle([0,PAGE_H-8,PAGE_W,PAGE_H], fill=ACCENT)

pages = []
p = Image.new("RGB", (PAGE_W, PAGE_H), BG); d = ImageDraw.Draw(p)
text_page(d, "Kestrel UI Review Package",
    ["Whole-product UI review: the React app (primary), its dialogs and views,",
     "and the marketing site — with the shared design system reference."],
    ["Repository: Kestrel Company Brain",
     "Screens: 28 captures — desktop 1440/1280, tablet 768, mobile 390, OG card 1200×630",
     "Treat every screenshot as current-state evidence.",
     "Return concrete, token-grounded upgrade recommendations (see final pages).",
     "",
     "Groups: App core (01–05) · Marketing/brand (06–19, 23–26) ·",
     "Appendix/debug (20–22) · App graph view mobile+desktop (27–28)"])
pages.append(p)

p = Image.new("RGB", (PAGE_W, PAGE_H), BG); d = ImageDraw.Draw(p)
text_page(d, "Theme reference — “like ZCode”",
    ["Dark charcoal surfaces, ONE warm orange accent, ivory text.",
     "The same tokens drive the app (frontend/src/index.css) and the marketing site."],
    ["Surfaces   bg #1a1a1a · bg-2 #161616 · panel #212121 · panel-2 #2b2b2b · panel-3 #333",
     "Text        ink/ivory #f2f0ec · ink-2 #d6d2ca · muted #a8a49d",
     "Accent      #E8873A (primary) · hover #F49D54 · dim rgba(232,134,59,.12) · on-accent #1a1206",
     "Lines       #2e2e2e / #3a3a3a · radius 12px cards · 9999px pills · focus ring 2px orange",
     "Type        Inter — titles 22–58px semibold, body 13.5–16.5px, labels 9.5–12px caps",
     "Components  shadcn/ui vendored: button, input, badge, dialog, dropdown, popover,",
     "            radio-group, switch, tooltip, command, separator, scroll-area, skeleton, sheet",
     "",
     "Rules: one accent only; dark-first; honest empty/disabled states with reasons;",
     "AA contrast both themes; reduced-motion; no decorative gradients on copy."])
x = 90
for (name, c) in [("bg",BG),("panel",PANEL),("accent",ACCENT),("ink",INK),("muted",MUTED)]:
    d.rectangle([x, 980, x+240, 1100], fill=c, outline=(58,58,58), width=2)
    d.text((x, 1110), name, font=font(26), fill=MUTED); x += 300
pages.append(p)

GROUPS = [
    ("App core views (React frontend)", [
        ("01-app-slack-dialog-initial.png", "Slack 'Configure access' dialog — initial state"),
        ("02-app-slack-dialog-toggled.png", "Slack dialog — read-only selected, private switch on"),
        ("03-app-connectors-cards-detail.png", "Connectors view — Slack/Google cards, honest states"),
        ("04-app-slack-dialog-final.png", "Slack dialog — final state after toggles"),
        ("05-app-chat-home-attachment-chips.png", "Chat home — greeting, prompt box, attachment chips"),
    ]),
    ("Marketing site — brand & hero", [
        ("06-marketing-hero-first-render.png", "Hero — first render (static fallback visible)"),
        ("07-marketing-hero-revealed.png", "Hero — after reveal fix, content visible"),
        ("13-marketing-hero-final.png", "Hero — final desktop composition"),
        ("26-marketing-hero-final-polished.png", "Hero — final after polish pass"),
    ]),
    ("Marketing site — sections & responsive", [
        ("10-marketing-product-demo.png", "Product demo — simulated app walkthrough"),
        ("23-marketing-how-it-works.png", "How it works — three-step cards"),
        ("24-marketing-features-midreveal.png", "Capabilities grid — mid reveal (motion evidence)"),
        ("25-marketing-features-settled.png", "Capabilities grid — settled 3×2"),
        ("15-marketing-tablet-768.png", "Tablet 768 — stacked hero + scene"),
        ("16-marketing-mobile-390.png", "Mobile 390 — hamburger nav"),
        ("17-marketing-mobile-menu.png", "Mobile — menu open (4 links + CTA)"),
        ("18-marketing-mobile-faq.png", "Mobile — FAQ accordion open"),
        ("19-marketing-og-card-1200x630.png", "OG social card 1200×630 (live capture)"),
    ]),
    ("App graph view (new) — desktop & mobile", [
        ("27-app-graph-mobile-390.png", "Graph view — mobile 390, overlay sidebar"),
        ("28-app-graph-desktop-1440.png", "Graph view — desktop 1440, 93 nodes / 161 edges"),
    ]),
    ("Appendix — process/debug captures (context only)", [
        ("08-marketing-hero-scene-midfix.png", "Hero scene — mid-fix close-up"),
        ("09-marketing-hero-scene-corrected.png", "Hero scene — orientation corrected"),
        ("11-marketing-hero-after-orient.png", "Hero — after card orientation fix"),
        ("12-marketing-hero-after-flow.png", "Hero — after edge-flow fix"),
        ("14-marketing-hero-closeup.png", "Hero scene — final close-up"),
        ("20-marketing-fullpage-attempt1.png", "Full-page capture attempt 1 (stitching artifact)"),
        ("21-marketing-fullpage-attempt2.png", "Full-page capture attempt 2"),
        ("22-debug-reveal-stuck.png", "Reveal-debug capture (blank section pre-fix)"),
    ]),
]
total = sum(len(g[1]) for g in GROUPS)
n = 0
for title, shots in GROUPS:
    p = Image.new("RGB", (PAGE_W, PAGE_H), BG); d = ImageDraw.Draw(p)
    text_page(d, title, ["Group header — following pages are raw captures."],
              [f"{len(shots)} capture(s) in this group."])
    pages.append(p)
    for fname, caption in shots:
        n += 1
        p = Image.new("RGB", (PAGE_W, PAGE_H), BG)
        img_page(p, os.path.join(SCREENS, fname), n, total, caption, note=f"file: screens/{fname}")
        pages.append(p)

p = Image.new("RGB", (PAGE_W, PAGE_H), BG); d = ImageDraw.Draw(p)
text_page(d, "What we ask of you (the reviewer)",
    ["Blunt, specific, evidence-based UI review and beautification guidance."],
    ["1. Hierarchy & composition: per screen — what reads first, what's off, exact fixes.",
     "2. Spacing/density: a concrete spacing + type scale for the app shell (tokens above).",
     "3. Beautification: per-component upgrades (prompt box, thread, sidebar, dialogs,",
     "   graph, connectors) that stay inside the token system — no new frameworks.",
     "4. Empty/disabled states: better honest-state patterns (see dialog + graph shots).",
     "5. Consistency audit: deviations between app and marketing uses of the theme.",
     "6. Reference designs: give exact Tailwind/shadcn specs (classes, sizes, radii)",
     "   for your top 10 improvements, ranked by impact-per-effort.",
     "7. Accessibility: anything below AA on the dark theme, with corrections.",
     "Do NOT propose: new frameworks, light-first redesign, extra accent colors,",
     "glassmorphism on copy, or changes that break honest states."])
pages.append(p)
p = Image.new("RGB", (PAGE_W, PAGE_H), BG); d = ImageDraw.Draw(p)
text_page(d, "Context the reviewer needs",
    ["What each surface IS — so recommendations match reality."],
    ["React app (primary): chat + brains + graph + connectors.",
     "  CreateBrainDialog → /api/brains/v2 (durable jobs, per-file stages shown live).",
     "  Prompt box: streams NDJSON answers; citations resolve from provenance tables.",
     "  History: server-backed (save/list/load). Graph: /api/graph circle layout.",
     "  Connectors: Slack/Gmail/Drive with honest 'not configured' states.",
     "Legacy shell: full-featured fallback; graph page linked for deep interactivity.",
     "Marketing: static site, 3D hero (Three.js) with static SVG fallback,",
     "  simulated walkthrough built from the synthetic demo corpus.",
     "No fake data in the app: 'no workspaces connected' / 'OAuth not configured'",
     "  states are REAL (routes not yet configured by the founder).",
     "Ask-flow latency note: generation route currently rate-limited — screens with",
     "  empty answers reflect that, not missing UI."])
pages.append(p)

out = os.path.join(HERE, "docs", "ui-review", "UI_REVIEW_PACKAGE.pdf")
pages[0].save(out, save_all=True, append_images=pages[1:], resolution=150)
print("PDF pages:", len(pages), "| size MB:", round(os.path.getsize(out)/1e6, 1), "|", out)
