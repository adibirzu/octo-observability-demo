# GUI Redesign Brief (WS4)

**Decision required: visual direction.** User chose "full redesign direction".
Nothing is restyled until a direction + palette + typography is locked here.

## Current baseline (what exists)

- Server-rendered **Jinja2** templates — no React/Vue.
  - Shop: `shop/server/templates/{base,shop,dashboard,login,genai_observability,ai_studio_login}.html`
  - CRM: `crm/server/templates/{base,catalog,products,simulation,captured_data,login}.html`
- Shop styling: **inline `:root` design system** in `base.html` — dark theme,
  Orbitron + Inter, CSS vars (`--teal #6cd2e0`, `--amber #ffbd59`, `--rose`, `--ok`),
  radial+linear gradient background, `--shadow` elevation.
- CRM styling: `crm/server/static/css/style.css` (1130 lines) — separate, duplicated palette.
- Assets: `octo-logo.svg`, product imagery under `static/img/products/`.

## Constraints

- Keep Jinja server-rendering (no SPA rewrite).
- Compositor-friendly motion only (`transform`/`opacity`/`clip-path`).
- A11y: WCAG-contrast, focus-visible rings, `prefers-reduced-motion`, semantic landmarks.
- Performance budget: microsite-class — CSS < 15kb where practical, two font families max.
- Observability is the product — data-viz must read as designed, not bolted on.

## Direction — LOCKED: Bento control-room (2026-06-04)

Evolve the existing dark identity into a **modular bento "control room."** Tiled
dashboard composition, strong scale-contrast hierarchy, and **data-viz as first-class
cards** (sparklines, status chips, MELT-correlation tiles, checkout-evidence receipt).
Lowest identity risk, highest demo impact for an observability product.

### Palette (semantic roles — evolve current tokens)

| Role | Token | Value | Use |
|------|-------|-------|-----|
| Surface base | `--bg` | `#07111c` | page background (radial+linear gradient kept) |
| Tile surface | `--bg-panel` | `rgba(9,20,34,0.78)` | bento tile fill |
| Hairline | `--line` | `rgba(140,190,230,0.14)` | tile borders / dividers |
| Ink | `--ink` | `#eef6ff` | primary text |
| Muted | `--muted` | ⚠ verify contrast ≥ 4.5:1 on tiles | secondary text |
| Primary accent | `--teal` | `#6cd2e0` | live/ok, links, focus ring |
| Signal | `--amber` | `#ffbd59` | warn / attention |
| Alert | `--rose` | `#ff6b7a` | error / decline |
| Success | `--ok` | `#5be59f` | healthy |
| Elevation | `--shadow` | `0 24px 60px rgba(3,10,18,.48)` | tile depth |

### Type

- **Display:** Orbitron (500/700/900) — tile labels, metric numerals, wordmark.
- **Text:** Inter (400/500/600) — body, evidence, table data.
- Scale: fluid `clamp()` — hero metric ≫ tile label ≫ body. Tabular-nums for metrics.

### Surface order (WS4b)

1. `shop/server/templates/base.html` — token sheet + bento shell + topbar.
2. `dashboard.html` + `genai_observability.html` — the bento tiles (data-viz).
3. `shop.html` — product grid as bento.
4. `login.html` / `ai_studio_login.html` — minimal branded cards.
5. CRM surfaces — adopt the shared token sheet.

### Locked checklist

- [x] Direction chosen — **Bento control-room**
- [x] Palette (semantic roles)
- [x] Type pairing + scale
- [ ] WS4a: shared token sheet extracted (shop inline + crm style.css → one source)
- [ ] Grounded by `gui-redesign-review` workflow punch list (running)
