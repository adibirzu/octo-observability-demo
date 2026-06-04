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

## Direction options (pick one)

1. **Dark luxury / control-room** — evolve the current dark theme into a disciplined,
   high-contrast "mission control" look. Lowest risk; reuses existing tokens.
2. **Glassmorphism with real depth** — layered translucent panels over the gradient,
   for an observability-HUD feel. Medium risk.
3. **Editorial / Swiss** — light, typographic, grid-driven; bold scale contrast.
   Biggest departure from current dark identity.
4. **Bento** — modular tiled dashboards; great for the observability surfaces, strong
   hierarchy. Pairs well with #1 or #2.

## To lock before WS4a/WS4b

- [ ] Direction chosen
- [ ] Palette (light/dark, semantic roles)
- [ ] Type pairing (display + text) and scale
- [ ] 2–3 references
- [ ] Surface order (which template first)
