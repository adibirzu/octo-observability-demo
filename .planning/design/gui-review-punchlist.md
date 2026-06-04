# GUI Review Punch List (WS4)

Source: `gui-redesign-review` workflow (5 agents, 4 lenses) — 2026-06-04.
36 findings → 27 after dedupe. Grounds WS4a/WS4b. Severity: HIGH → MEDIUM → LOW.

Legend: ✅ done · ⬜ pending

## Shared base / cross-app (`base.html` + tokens)

### HIGH
- ✅ **Global `:focus-visible` ring** — added to `base.html` (`:where(...)` 2px teal). *(a11y 2.4.7)*
- ✅ **`prefers-reduced-motion` guard** — added to `base.html` (kills transitions + hover transforms). *(a11y 2.3.3)*
- ✅ **Heading scale h1–h4** — distinct sizes added in `base.html` (was one flat weight). *(hierarchy)*
- ⬜ **Single token source** — extract `shop/server/static/css/tokens.css`; 3 palettes drift (`base.html:8-21` vs CRM `style.css:1-18` vs `shop.html:4-22`). *(consistency)* → **WS4a**
- ⬜ **Unify token names** — shop `--bg/--ink/--muted` vs CRM `--bg-base/--text-primary/--text-secondary`. Adopt `--color-surface/-text/-text-muted/-line/-success`. *(consistency)* → **WS4a**
- ⬜ **Drop `--shop-*` shadow palette** — `shop.html:4-22` re-declares a full parallel system; map onto shared tokens, keep only radius scale. *(consistency)* → **WS4a**

### MEDIUM
- ✅ **Skip-to-content link + `#main-content`** — added to `base.html`. *(a11y 2.4.1)*
- ⬜ **Radius/elevation scale** — uniform 24px + one shadow everywhere; introduce depth tiers. *(hierarchy)* → **WS4b**
- ⬜ **Tokenize radius/spacing magic numbers** — 24/26/16px card radii across files. *(consistency)* → **WS4a**
- ⬜ **Typography tokens** — `--font-body/-display/-mono` + single `@import`; fonts diverge per file. *(consistency)* → **WS4a**
- ⬜ **Shared `.btn`/`.badge` component sheet** — base vs CRM render differently. *(consistency)* → **WS4b**

### LOW
- ⬜ **Move font `@import` to top** of stylesheet (spec-invalid after `:root`). → **WS4a**
- ⬜ **Spacing scale** `--space-xs/sm/md/lg` (uniform 18-24px rhythm). → **WS4a**

## Shop storefront (`shop.html`)
### HIGH
- ⬜ Product grid 280px floor overflows 960–1200px → `repeat(auto-fit, minmax(min(100%,260px),1fr))`. *(responsive)*
- ⬜ Fixed 360px sidebar overflows at 1024px → `minmax(280px,360px)` / raise breakpoint. *(responsive)*
- ⬜ `--shop-dim` #6b7682 fails contrast 3.87:1 → ≥ #8a96a2. *(a11y 1.4.3)*
- ⬜ Primary vs secondary `.btn` indistinct → accent-fill primary, outline secondary. *(hierarchy)*
### MEDIUM
- ⬜ Cart remove / copy-evidence buttons < 24×24 → min 24px. *(a11y 2.5.8)*
- ⬜ `✕` remove button no accessible name → `aria-label`. *(a11y 4.1.2)*
- ⬜ `.cat-btn` no `:active` state. *(hierarchy)*
### LOW
- ⬜ Hero 300px min defensively → `minmax(0,.55fr)`. *(responsive)*
- ⬜ Product `<img> onerror display:none` hides content → text placeholder. *(a11y 1.1.1)*

## GenAI Observability (`genai_observability.html`)
### HIGH
- ⬜ 8-col table no scroll wrapper → `overflow-x:auto`. *(responsive)*
### MEDIUM
- ⬜ Controls row no `flex-wrap` → wrap at 320px. *(responsive)*
### LOW
- ⬜ Flat tiles/link cards → elevation + hover lift. *(hierarchy)*
- ⬜ `—` placeholder tiles no "no data" aria; `<select>` focus (covered by global fix). *(a11y)*
- ⬜ Trace-id `<code>` no wrap guard → `overflow-wrap:anywhere`. *(responsive)*
- ⬜ Inline `<style>` → `{% block head %}` + base utilities. *(consistency)*

## Dashboard (`dashboard.html`)
### HIGH
- ⬜ Metric label vs value compete (both Orbitron caps) → label small/muted. *(hierarchy)*
### MEDIUM
- ⬜ No `<h1>` (top is `<h2>`) → promote. *(a11y 1.3.1)*
### LOW
- ⬜ Decorative hero logo redundant alt → `alt=""`. *(a11y 1.1.1)*
- ⬜ Recent-orders table: overflow wrapper + `scope`/caption. *(responsive+a11y)*
- ⬜ Flat "Loading…" → skeletons. *(hierarchy)*

## CRM (`crm/server/static/css/style.css`)
### MEDIUM
- ⬜ Non-catalog data tables no overflow wrapper → shared rule. *(responsive)*
- ⬜ Content-header 2.35rem H1 + buttons overflow at 768 → `flex-wrap` + fluid clamp. *(responsive)*
- ⬜ Sidebar not a `<nav>` landmark → wrap. *(a11y)*
### LOW
- ⬜ `--text-muted` #6a8794 borderline 4.54:1 → ≈ #7e9aa6. *(a11y 1.4.3)*

---

## Execution order

1. **WS4a** — `tokens.css` (palette/naming/radius/space/font tokens) + wire `base.html`, then remap `--shop-*` and CRM palette onto it. Move font `@import`. *(consistency HIGHs)*
2. **WS4b** — bento restyle: depth/elevation scale, metric-label hierarchy, primary/secondary CTAs, responsive grid/table fixes, shared `.btn`/`.badge`, contrast nudges, skeletons.
3. **WS4c** — Playwright screenshots 320/768/1024/1440 + automated a11y; diff before/after.

Cross-cutting a11y HIGHs (focus-visible, reduced-motion, heading scale, skip-link) already landed in `base.html`.
