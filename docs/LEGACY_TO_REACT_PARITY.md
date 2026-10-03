# Legacy HTML → React: Complete Feature & Design Parity Audit

**Date:** 2026-10-02  
**Legacy:** `static/` (index.html, graph.html, brains.html, upload.html, shell.js, ui.js, auth.js, shell.css)  
**React:** `frontend/src/` (App.tsx, Sidebar.tsx, PromptBox.tsx, SourceDrawer.tsx, GraphView.tsx, Connectors.tsx, CreateBrainDialog.tsx, SlackAccessDialog.tsx, Markdown.tsx, index.css, api.ts)

---

## 1. Design System

### 1.1 Color Palette ("Deck")

| Token | Legacy (shell.css) | React (index.css) | Match |
|---|---|---|---|
| `--bg` | `#1a1a1a` | `#1a1a1a` | ✅ |
| `--bg-2` | `#161616` | `#161616` | ✅ |
| `--panel` | `#232323` | `#212121` | ⚠️ Near-identical |
| `--panel-2` | `#2b2b2b` | `#2b2b2b` | ✅ |
| `--panel-3` | `#333333` | `#333333` | ✅ |
| `--line` | `rgba(255,255,255,.08)` | `rgba(255,255,255,0.08)` | ✅ |
| `--line-2` | `rgba(255,255,255,.13)` | `rgba(255,255,255,0.13)` | ✅ |
| `--line-3` | `rgba(255,255,255,.22)` | `rgba(255,255,255,0.22)` | ✅ |
| `--fg` | `#e9e9e9` | `#ececec` | ⚠️ Near-identical |
| `--fg-2` | `#c9c9c9` | `#c9c9c9` | ✅ |
| `--muted` | `#9b9b9b` | `#9a9a9a` | ⚠️ Near-identical |
| `--muted-2` | `#949494` | `#6b6b6b` | ❌ React darker |
| `--accent` | `#e8863b` | `#e8873a` | ⚠️ Near-identical |
| `--accent-2` | `#f49d54` | `#f49d54` | ✅ |
| `--accent-ink` | `#161616` | `#1a1206` | ⚠️ Near-identical |
| `--good` | `#4ade80` | `#4ade80` | ✅ |
| `--bad` | `#f07070` | `#f07070` | ✅ |
| `--warn` | `#e5c07b` | `#e5c07b` | ✅ |
| `--wash` | `rgba(255,255,255,.05)` | `rgba(255,255,255,0.05)` | ✅ |
| `--wash-2` | `rgba(255,255,255,.07)` | `rgba(255,255,255,0.07)` | ✅ |
| `--radius` | `14px` | `12px` | ⚠️ React slightly smaller |
| `--radius-sm` | `10px` | — | ❌ Not defined |
| `--radius-xs` | `7px` | — | ❌ Not defined |

### 1.2 Light Theme

| Token | Legacy | React | Match |
|---|---|---|---|
| `--bg` | `#f7f5f2` | `#f7f5f2` | ✅ |
| `--panel` | `#ffffff` | `#ffffff` | ✅ |
| `--accent` | `#b45309` | `#b45309` | ✅ |
| `--muted-2` | `#6f6a60` | `#6f6a60` | ✅ |
| `--bad` | `#c53030` | `#c53030` | ✅ |

### 1.3 Typography

| Property | Legacy | React | Match |
|---|---|---|---|
| Font family | `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif` | `"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` | ⚠️ React adds Inter |
| Body size | `15px/1.62` | `14.5px/1.6` | ⚠️ React slightly smaller |
| h1 | `26px/600/-.02em` | `22px/semibold/-.02em` | ⚠️ React smaller |
| h2 | `17px/600` | `15px/semibold` | ⚠️ React smaller |
| Label/overline | `10px/700/.15em/uppercase` | `9.5px/700/.15em/uppercase` | ⚠️ React slightly smaller |
| Mono | `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace` | `font-mono` (Tailwind default) | ⚠️ Different stack |

### 1.4 Spacing & Layout

| Property | Legacy | React | Match |
|---|---|---|---|
| Sidebar width | `268px` | `268px` | ✅ |
| Content max-width | `820px` | `780px` | ⚠️ React narrower |
| Home max-width | `680px` | `820px` | ❌ React wider |
| Thread padding | `36px 24px 210px` | `py-10 px-6` | ⚠️ Different |
| Card radius | `14px` | `12px` | ⚠️ React smaller |
| Composer padding | `22px 44px 18px` | `px-4 py-3` | ⚠️ Different |

---

## 2. Page-by-Page Feature Audit

### 2.1 Home / Chat Page (`/`)

#### 2.1.1 Home State (No Active Chat)

| Feature | Legacy | React | Status |
|---|---|---|---|
| Watermark `◆` | ✅ 150px, `--watermark` color | ❌ Not present | ❌ **MISSING** |
| Greeting | ✅ Time-aware (morning/afternoon/evening) | ✅ Time-aware | ✅ |
| Greeting text | `30px/550/-.02em` | `30px/semibold/-.02em` | ✅ |
| Suggestion chips | ✅ 8 chips (4 demo + 4 general) | ✅ 4 chips (general only) | ⚠️ **PARTIAL** — demo chips missing |
| Chip style | `999px` pill, `--line-2` border, hover accent | `rounded-full` pill, `border-border`, hover accent | ✅ |
| Composer (home mode) | ✅ Centered, max-width 680px, watermark above | ✅ Centered, max-width 820px | ⚠️ Width differs |
| Brand glow | ❌ Not present | ✅ `bg-accent-glow blur-2xl` behind brand mark | ✅ React adds |

#### 2.1.2 Composer

| Feature | Legacy | React | Status |
|---|---|---|---|
| Brain selector | ✅ Dropdown with brain list | ✅ Dropdown with brain list | ✅ |
| Brain chip style | `bar-btn` with `◆` + name + chevron | `rounded-full` with `◆` + name + `▾` | ✅ |
| Textarea | ✅ Auto-resize, max-height 140px | ✅ Auto-resize, max-height 140px | ✅ |
| Placeholder | "Ask across every document the company has written…" | Same | ✅ |
| Send button | ✅ 34px circle, `--btn-ink` background, arrow icon | ✅ 36px circle, `bg-primary`, Send icon | ✅ |
| Stop button | ✅ Red background, square icon | ✅ `bg-primary`, Square icon | ✅ |
| Attach button | ✅ `+` icon, opens file picker | ✅ `+` icon, opens file picker | ✅ |
| File chips | ✅ 64×64 thumbnails with remove | ✅ Text chips with remove | ⚠️ Different style |
| Drag-and-drop | ✅ On composer | ✅ On composer | ✅ |
| Keyboard hint | ❌ Not present | ✅ `↵ send` / `⇧↵ new line` | ✅ React adds |
| Focus ring | ✅ `--line-3` border on focus-within | ✅ `border-accent/60` + shadow | ✅ |
| Stage label | ✅ Shows pipeline stage | ✅ Shows pipeline stage | ✅ |
| `?brain=` display | ✅ Shows current brain in corner | ✅ Shows `?brain=` in corner | ✅ |

#### 2.1.3 Chat Thread

| Feature | Legacy | React | Status |
|---|---|---|---|
| User turn style | Card: `panel-2` bg, `16px 16px 6px 16px` radius, max-width 85% | `bg-wash-2`, `rounded-2xl rounded-br-md`, max-width 85% | ⚠️ Different bg |
| Bot turn style | Plain text, `15.5px/1.8`, `--fg-2` | `text-foreground/90`, Markdown rendered | ✅ |
| Turn animation | `rise` keyframe: `translateY(8px)` → none, 180ms | ❌ Not present | ❌ **MISSING** |
| Streaming cursor | `▍` blinking (1s steps) | Pulsing rectangle `bg-accent/80` | ✅ Different style |
| Markdown rendering | ✅ h3/h4/h5, p, ul/ol, strong, code, table | ✅ Full Markdown component | ✅ |
| Code blocks | Inline: `panel-2` bg, mono | Inline: `bg-panel-2`, mono | ✅ |
| Tables | Full table with header styling | Full table with header styling | ✅ |

#### 2.1.4 Message Actions (Hover Controls)

| Feature | Legacy | React | Status |
|---|---|---|---|
| Hover reveal | `opacity: 0` → `opacity: 1` on `.turn:hover` | `opacity-0` → `opacity-100` on `group-hover/turn` | ✅ |
| Copy button | ✅ Copies answer text | ✅ Copies answer text | ✅ |
| Email draft | ✅ Opens draft box | ❌ Not present | ❌ **MISSING** |
| Next steps | ✅ Generates action checklist | ❌ Not present | ❌ **MISSING** |
| Chat update | ✅ Generates Slack/Teams message | ❌ Not present | ❌ **MISSING** |
| Thumbs up/down | ✅ Feedback buttons | ❌ Not present | ❌ **MISSING** |
| Timestamp | ✅ Shows time | ✅ Shows time | ✅ |
| Regenerate | ❌ Not present | ✅ Re-asks previous question | ✅ React adds |

#### 2.1.5 Citations / Sources

| Feature | Legacy | React | Status |
|---|---|---|---|
| Source chips | ✅ Mono 11px, `--line-2` border, hover accent | ✅ Mono 11px, `border-border`, hover accent | ✅ |
| "Grounded in N sources" | ❌ Not present | ✅ Label above chips | ✅ React adds |
| Source modal | ✅ Full document text, highlighted passage | ✅ Full document text, cited passage | ✅ |
| Source drawer | ❌ Not present (modal) | ✅ Right-side drawer (420px) | ✅ React adds |
| Origin label | ✅ "CORPUS" / "TENANT" / "durable" | ✅ Origin label | ✅ |
| Copy button | ✅ Copies source text | ❌ Not present | ❌ **MISSING** |
| Unresolved state | ✅ "This reference could not be opened" | ✅ Same | ✅ |

#### 2.1.6 Working Log (Pipeline Narration)

| Feature | Legacy | React | Status |
|---|---|---|---|
| Stage display | ✅ Real engine steps with durations | ✅ Stage label in composer | ✅ |
| Collapsible log | ✅ `.working.collapsed` hides steps | ❌ Not present | ❌ **MISSING** |
| Spinner | ✅ CSS `spin` animation | ✅ Pulsing dot | ✅ |
| Step states | ✅ `done` / `live` / `stopped` | ❌ Not present | ❌ **MISSING** |
| Elapsed time | ✅ `w-elapsed` counter | ❌ Not present | ❌ **MISSING** |

#### 2.1.7 Suggestion Chips (Post-Answer)

| Feature | Legacy | React | Status |
|---|---|---|---|
| Answer-derived suggestions | ✅ Flows at foot of every turn | ❌ Not present | ❌ **MISSING** |
| Action prompts | ✅ Includes action prompts | ❌ Not present | ❌ **MISSING** |

#### 2.1.8 Export

| Feature | Legacy | React | Status |
|---|---|---|---|
| Export Markdown | ✅ From `⋯` menu | ❌ Not present | ❌ **MISSING** |
| Export plain text | ✅ From `⋯` menu | ❌ Not present | ❌ **MISSING** |
| Export Word | ✅ From `⋯` menu | ❌ Not present | ❌ **MISSING** |
| Export PDF | ✅ From `⋯` menu | ❌ Not present | ❌ **MISSING** |
| Copy transcript | ✅ From `⋯` menu | ❌ Not present | ❌ **MISSING** |

#### 2.1.9 Add Documents (In-Chat)

| Feature | Legacy | React | Status |
|---|---|---|---|
| Add files to brain | ✅ From `⋯` menu, opens files sheet | ✅ Auto-ingest on attach | ✅ Different UX |
| Files sheet | ✅ Drag-drop, per-file status | ❌ Not present | ❌ **MISSING** |
| Pipeline progress | ✅ Real states streamed | ❌ Not present | ❌ **MISSING** |

#### 2.1.10 Left Rail (Message Scrubber)

| Feature | Legacy | React | Status |
|---|---|---|---|
| Jump to user message | ✅ `#rail` with tick marks | ❌ Not present | ❌ **MISSING** |
| Active tick highlight | ✅ `.here` class, accent color | ❌ Not present | ❌ **MISSING** |
| Hover tooltip | ✅ `#rail-tip` with title | ❌ Not present | ❌ **MISSING** |

#### 2.1.11 Jump to Latest

| Feature | Legacy | React | Status |
|---|---|---|---|
| Jump-to-latest pill | ✅ Fixed bottom-right, appears when scrolled up | ❌ Not present | ❌ **MISSING** |

#### 2.1.12 Auth Gate

| Feature | Legacy | React | Status |
|---|---|---|---|
| Sign-in gate | ✅ Full-screen overlay, Clerk mounted via `mountSignIn` into `#clerk-mount` | ✅ Full-screen overlay, Clerk `openSignIn()` modal with theme-matched appearance | ✅ FIXED |
| Blur app when locked | ✅ `filter: blur(6px) saturate(.6)` on `.app-main` | ✅ `blur` class applied via `body.locked` equivalent | ✅ FIXED |
| Clerk theming | ✅ Theme-matched appearance (light/dark vars) | ✅ Same CSS vars in `AuthGate.tsx` | ✅ FIXED |
| Sign out | `window.KestrelAuth.signOut()` | SettingsMenu → `Clerk.signOut()` | ✅ |
| Account modal | `window.KestrelAuth.openAccount()` → `Clerk.openUserProfile()` | SettingsMenu → same | ✅ |
| Social buttons | ✅ Styled for dark/light | ❌ Not present | ❌ **MISSING** |

#### 2.1.13 Restore / Switch Animations

| Feature | Legacy | React | Status |
|---|---|---|---|
| Restore overlay | ✅ `#restore` covers page during `?chat=` load | ❌ Not present | ❌ **MISSING** |
| Switch animation | ✅ `#switch-fx` dims + spinner on chat switch | ❌ Not present | ❌ **MISSING** |

---

### 2.2 Graph Page (`/graph`)

| Feature | Legacy | React | Status |
|---|---|---|---|
| Full interactive canvas | ✅ Force-directed layout, pan/zoom | ❌ Simplified SVG circle layout | ❌ **MISSING** |
| Node expansion | ✅ Click core node → sub-nodes | ❌ Not present | ❌ **MISSING** |
| Node inspector | ✅ Right panel: type, properties, connections | ✅ Basic: label, id, degree | ⚠️ **PARTIAL** |
| Properties display | ✅ Key-value pairs, capped at 420 chars | ❌ Not present | ❌ **MISSING** |
| Relationships list | ✅ Grouped by verb, clickable | ❌ Not present | ❌ **MISSING** |
| Zoom controls | ✅ +/−/fit/expand-all/collapse | ❌ Not present | ❌ **MISSING** |
| Exit node view | ✅ Large labelled button | ❌ Not present | ❌ **MISSING** |
| Legend | ✅ Color by node type with counts | ✅ Basic legend (3 items) | ⚠️ **PARTIAL** |
| Focus gradient | ✅ Black gradient behind focused node | ❌ Not present | ❌ **MISSING** |
| Node labels | ✅ At zoom > 0.85, truncated at 34 chars | ✅ Always shown, truncated at 26 chars | ⚠️ Different |
| Drag to pan | ✅ | ❌ Not present | ❌ **MISSING** |
| Scroll to zoom | ✅ Zoom toward pointer | ❌ Not present | ❌ **MISSING** |
| `?brain=` scoping | ✅ | ✅ | ✅ |
| Empty state | ✅ "Run ingest.py first" / "ingestion may still be running" | ✅ "graph is empty" | ✅ |
| Error state | ✅ "Could not load the graph: ..." | ✅ "Could not load the graph: ..." | ✅ |
| >120 node truncation | ❌ Not present | ✅ With honest label | ✅ React adds |
| Link to legacy | ❌ IS the legacy | ✅ "full interactive graph" link | ✅ React adds |

---

### 2.3 Brains Page (`/brains`)

| Feature | Legacy | React | Status |
|---|---|---|---|
| Brain list | ✅ All brains with stats | ❌ Not present (sidebar only) | ❌ **MISSING** |
| Brain stats | ✅ Nodes · edges count | ❌ Not present | ❌ **MISSING** |
| Demo badge | ✅ "demo" badge | ❌ Not present | ❌ **MISSING** |
| System badge | ✅ "system" badge | ❌ Not present | ❌ **MISSING** |
| Open link | ✅ `/?brain=<name>` | ✅ Via brain selector | ✅ |
| Graph link | ✅ `/graph?brain=<name>` | ✅ Via graph view | ✅ |
| Add documents link | ✅ `/upload?brain=<name>` | ❌ Not present | ❌ **MISSING** |
| Delete brain | ✅ Two-step confirm, inline | ❌ Not present | ❌ **MISSING** |
| New brain button | ✅ Links to `/upload` | ✅ "New brain" in sidebar | ✅ |
| Empty state | ✅ "No brains yet" | ✅ "No saved chats yet" | ⚠️ Different |
| Footer links | ✅ demo dashboard, all brains, /health | ❌ Not present | ❌ **MISSING** |

---

### 2.4 Upload Page (`/upload`)

| Feature | Legacy | React | Status |
|---|---|---|---|
| Brain name input | ✅ With validation hint | ✅ In CreateBrainDialog | ✅ |
| Drag-and-drop zone | ✅ 5MB per file, 40 max | ✅ In CreateBrainDialog | ✅ |
| File list | ✅ With size, remove button | ✅ With name chips | ✅ |
| Build button | ✅ Disabled until name + files | ✅ Disabled until name + files | ✅ |
| Ingestion progress | ✅ Real pipeline states streamed | ✅ Job status polling | ✅ |
| Per-file status | ✅ ok/bad/warn with colors | ✅ Per-file stage in job | ✅ |
| 409 handling | ✅ "Add to existing" offer | ❌ Not present | ❌ **MISSING** |
| `?brain=` prefill | ✅ Pre-fills name, warns | ❌ Not present | ❌ **MISSING** |
| Done state | ✅ "Ready. Open the dashboard for X" | ✅ Job SUCCEEDED state | ✅ |
| Error state | ✅ "Ingestion failed: ..." | ✅ Job FAILED state | ✅ |
| Log cap | ✅ 60 lines max | ❌ Not present | ❌ **MISSING** |

---

### 2.5 Sidebar

#### 2.5.1 Navigation

| Feature | Legacy | React | Status |
|---|---|---|---|
| Brand mark | ✅ `◆` gradient box | ✅ `◆` primary box | ✅ |
| Brand name | ✅ "Kestrel" + "Company Brain" | ✅ Same | ✅ |
| Nav items | ✅ New chat, New brain, Brains, Graph | ✅ New chat, New brain, Graph, Connectors | ✅ |
| Active state | ✅ `--wash-2` bg, accent left bar | ✅ `bg-sidebar-accent` | ✅ |
| Icons | ✅ SVG (ask, upload, brains, graph) | ✅ Lucide icons | ✅ |
| `?brain=` preservation | ✅ Carried across navigation | ✅ Via URL params | ✅ |

#### 2.5.2 Chat List

| Feature | Legacy | React | Status |
|---|---|---|---|
| Grouped by brain | ✅ Folders with collapse | ✅ Folders with collapse | ✅ |
| Chat items | ✅ Title, time, delete | ✅ Title, delete | ✅ |
| Active chat | ✅ Highlighted | ✅ Highlighted | ✅ |
| Delete chat | ✅ Two-step confirm | ✅ Two-step confirm | ✅ |
| Delete all in brain | ✅ `group-del` action | ❌ Not present | ❌ **MISSING** |
| Search | ❌ Not present | ✅ Search input | ✅ React adds |
| Sort (updated/created) | ✅ View menu | ❌ Not present | ❌ **MISSING** |
| Timeline view | ✅ Flat list, sorted by time | ❌ Not present | ❌ **MISSING** |
| View toggle | ✅ Brain/Timeline modes | ❌ Not present | ❌ **MISSING** |
| Server hydration | ✅ Merges Postgres chats | ✅ Server-backed | ✅ |
| Cross-brain history | ✅ All brains' chats listed | ✅ All brains' chats listed | ✅ |
| Chat count cap | ✅ 16 per brain, 14 timeline | ✅ 16 per brain | ✅ |
| Relative time | ✅ "now", "5m", "2h", "3d" | ❌ Not present | ❌ **MISSING** |
| Empty state | ✅ "No saved chats yet" | ✅ "No saved chats yet" | ✅ |

#### 2.5.3 Sidebar Animations

| Feature | Legacy | React | Status |
|---|---|---|---|
| Gliding hover rail | ✅ `.sb-slide` element slides between rows | ❌ Not present | ❌ **MISSING** |
| Tick in gutter | ✅ Shrinks to 2px tick tracking cursor | ❌ Not present | ❌ **MISSING** |
| Collapse/expand | ✅ `translateX` animation | ✅ `transition-[width]` | ✅ |
| Mobile off-canvas | ✅ Slide in/out | ✅ `max-md:fixed` + `translate-x` | ✅ |

#### 2.5.4 User Area & Settings

| Feature | Legacy | React | Status |
|---|---|---|---|
| User avatar | ✅ Initials or image | ❌ Not present | ❌ **MISSING** |
| User name/email | ✅ From Clerk | ❌ Not present | ❌ **MISSING** |
| Settings gear | ✅ Opens settings menu | ❌ Not present | ❌ **MISSING** |
| Language selector | ✅ 6 languages (en/hi/es/fr/de/zh) | ❌ Not present | ❌ **MISSING** |
| Theme selector | ✅ System/Dark/Light | ❌ Not present | ❌ **MISSING** |
| Usage stats | ✅ Table with feature/brain/model/calls/tokens | ❌ Not present | ❌ **MISSING** |
| Upgrade plans | ✅ 3 tiers (Starter/Pro/Business) | ❌ Not present | ❌ **MISSING** |
| Manage account | ✅ Clerk account modal | ❌ Not present | ❌ **MISSING** |
| Sign out | ✅ Ends session | ❌ Not present | ❌ **MISSING** |
| Sign in button | ✅ When not signed in | ❌ Not present | ❌ **MISSING** |

---

### 2.6 Connectors Page

| Feature | Legacy | React | Status |
|---|---|---|---|
| Slack section | ✅ Configure access, workspaces, import | ✅ Configure access, workspaces | ✅ |
| Google section | ✅ Gmail import, Drive import | ✅ Gmail connect | ⚠️ **PARTIAL** — Drive missing |
| Email send | ✅ "Send on approval" section | ❌ Not present | ❌ **MISSING** |
| Slack send | ✅ "Send on approval" section | ❌ Not present | ❌ **MISSING** |
| Import controls | ✅ Channel ID, brain, search query | ❌ Not present | ❌ **MISSING** |
| OAuth connect | ✅ Popup flow | ✅ Redirect flow | ✅ |
| Disconnect | ✅ Per-provider | ✅ Per-workspace | ✅ |
| Status pills | ✅ Connected/Coming soon/Reconnect | ✅ Connected/Not configured | ✅ |
| Scope picker | ✅ Read+post / Read only / Private | ✅ Same | ✅ |
| Workspace list | ✅ With channels, post, disconnect | ✅ With disconnect | ⚠️ **PARTIAL** |

---

### 2.7 Settings Modals

#### 2.7.1 Usage Stats Modal

| Feature | Legacy | React | Status |
|---|---|---|---|
| Table | ✅ Feature, Brain, Model, Calls, Tokens | ❌ Not present | ❌ **MISSING** |
| Totals row | ✅ Calls, Tokens, Time | ❌ Not present | ❌ **MISSING** |
| Empty state | ✅ "No model calls recorded yet" | ❌ Not present | ❌ **MISSING** |
| Sign-in required | ✅ "Sign in to see usage" | ❌ Not present | ❌ **MISSING** |

#### 2.7.2 Upgrade Modal

| Feature | Legacy | React | Status |
|---|---|---|---|
| 3 tiers | ✅ Starter $20, Pro $50, Business $99 | ❌ Not present | ❌ **MISSING** |
| Features list | ✅ Checkmarks per tier | ❌ Not present | ❌ **MISSING** |
| Coming soon | ✅ Disabled buttons, honest copy | ❌ Not present | ❌ **MISSING** |

#### 2.7.3 Language Menu

| Feature | Legacy | React | Status |
|---|---|---|---|
| 6 languages | ✅ English, हिन्दी, Español, Français, Deutsch, 中文 | ❌ Not present | ❌ **MISSING** |
| Live re-render | ✅ `kestrel:lang` event | ❌ Not present | ❌ **MISSING** |
| Persistence | ✅ localStorage | ❌ Not present | ❌ **MISSING** |

#### 2.7.4 Theme Menu

| Feature | Legacy | React | Status |
|---|---|---|---|
| System/Dark/Light | ✅ 3 options with tick | ❌ Not present | ❌ **MISSING** |
| Live preview | ✅ `kestrel:theme` event | ❌ Not present | ❌ **MISSING** |
| Persistence | ✅ localStorage | ❌ Not present | ❌ **MISSING** |

---

## 3. Animations & Transitions

| Animation | Legacy | React | Status |
|---|---|---|---|
| Turn rise | `@keyframes rise` 180ms | ❌ Not present | ❌ **MISSING** |
| Streaming blink | `@keyframes blink` 1s steps | Pulsing (different) | ✅ |
| Pop menu | `@keyframes pop` 160ms | ❌ Not present | ❌ **MISSING** |
| Sheet modal | `@keyframes sheet` 160ms scale | ❌ Not present | ❌ **MISSING** |
| Spin | `@keyframes spin` 0.8s linear | `animate-pulse` | ✅ |
| Slide rail | `cubic-bezier(.3,1.1,.3,1)` 260ms | ❌ Not present | ❌ **MISSING** |
| Sidebar collapse | `transform .2s ease` | `transition-[width] 200ms` | ✅ |
| Hover transitions | `.15s ease` on all interactive | `transition-colors 150ms` | ✅ |
| Focus ring | `--focus` shadow | `focus-visible:ring` | ✅ |
| Reduced motion | `@media (prefers-reduced-motion: reduce)` | Same | ✅ |

---

## 4. Internationalization

| Feature | Legacy | React | Status |
|---|---|---|---|
| 6 languages | ✅ en, hi, es, fr, de, zh | ❌ English only | ❌ **MISSING** |
| `data-i18n` attributes | ✅ Auto-applied on load | ❌ Not present | ❌ **MISSING** |
| `data-i18n-ph` placeholders | ✅ | ❌ Not present | ❌ **MISSING** |
| `data-i18n-title` titles | ✅ | ❌ Not present | ❌ **MISSING** |
| Language switch event | ✅ `kestrel:lang` | ❌ Not present | ❌ **MISSING** |

---

## 5. API Integration

| Feature | Legacy | React | Status |
|---|---|---|---|
| `/api/ask` streaming | ✅ NDJSON fetch + ReadableStream | ✅ Same | ✅ |
| `/api/graph` | ✅ | ✅ | ✅ |
| `/api/brains` | ✅ | ✅ | ✅ |
| `/api/chats` | ✅ Server + localStorage | ✅ Server-backed | ✅ |
| `/api/source` | ✅ | ✅ | ✅ |
| `/api/extract` | ✅ | ✅ | ✅ |
| `/api/connectors/status` | ✅ | ✅ | ✅ |
| `/api/connectors/slack/*` | ✅ | ✅ | ✅ |
| `/api/usage` | ✅ | ❌ Not present | ❌ **MISSING** |
| `/api/config` | ✅ | ✅ | ✅ |
| Auth headers | ✅ Clerk token | ✅ Clerk token | ✅ |

---

## 6. Summary: What Must Be Built

### Critical (User-Facing, High-Impact)

1. **Settings menu** — Language, Theme, Usage, Upgrade, Account, Sign out
2. **Auth gate** — Full-screen sign-in overlay with Clerk
3. **Message actions** — Email draft, Next steps, Chat update, Thumbs up/down
4. **Export** — Markdown, TXT, DOCX, PDF, Copy transcript
5. **Working log** — Collapsible pipeline narration with durations
6. **Suggestion chips** — Answer-derived, post-answer
7. **Left rail** — Message scrubber with jump-to-user
8. **Jump to latest** — Floating pill when scrolled up
9. **Graph page** — Full interactive canvas (force-directed, expand, inspector)
10. **Brains page** — Full list with stats, delete, add documents
11. **Upload page** — Full page with drag-drop, progress, 409 handling

### Important (Polish, Medium-Impact)

12. **Turn rise animation** — `@keyframes rise` on new turns
13. **Pop menu animation** — `@keyframes pop` on menus
14. **Sheet modal animation** — `@keyframes sheet` on modals
15. **Gliding hover rail** — `.sb-slide` element in sidebar
16. **Relative time** — "now", "5m", "2h", "3d" on chat items
17. **Sort/View toggle** — Brain/Timeline modes, Updated/Created sort
18. **Delete all chats in brain** — `group-del` action
19. **Restore/Switch animations** — Overlay during chat load/switch
20. **Source copy button** — In source drawer
21. **Demo suggestion chips** — 4 demo-specific chips on home
22. **Watermark** — Large `◆` on home state
23. **i18n** — 6 languages with live switch
24. **Theme selector** — System/Dark/Light with live preview

### Nice-to-Have (Low-Impact)

25. **Brand glow** — Already in React ✅
26. **Keyboard hints** — Already in React ✅
27. **Regenerate** — Already in React ✅
28. **Search chats** — Already in React ✅
29. **"Grounded in N sources"** — Already in React ✅
30. **Source drawer** — Already in React ✅

---

## 7. Recommended Build Order

1. **Settings menu + Auth gate** — Unblocks everything else
2. **Message actions + Export** — Core chat UX
3. **Working log + Suggestions** — Pipeline transparency
4. **Left rail + Jump to latest** — Navigation
5. **Graph page** — Full interactive canvas
6. **Brains page** — Full list management
7. **Upload page** — Full page experience
8. **Animations** — Rise, pop, sheet, slide rail
9. **i18n + Theme** — 6 languages, live theme switch
10. **Polish** — Relative time, sort/view, delete all, restore animations
