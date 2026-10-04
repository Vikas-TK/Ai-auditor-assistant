# UI/UX Overhaul Changelog

Frontend-only visual/UX pass on AI Auditor Assistant, bringing the app to an
enterprise-grade standard (Stripe Dashboard / Linear / Ramp tier) via a single
design-token system. No backend code, API contracts, routes, data, or ML/OCR/
RAG logic were touched at any step.

## Scope discipline

Per the governing constraint, every step only changed: CSS/styling, layout,
spacing, typography, colors, icons, animations, HTML markup structure,
visible copy, and purely presentational JS (toasts, modals, skeletons,
empty/error states, formatting). No element IDs, `name` attributes,
data-attributes, function names, API calls, request/response shapes, or
database/model logic were altered.

## Steps & commits

1. **Audit/screenshot** — baseline capture of every view before any edits.
2. **`8b40478`** — Design tokens + base components: CSS variables and
   reusable classes (`.fintech-card`, `.kpi-*`, `.toolbar`, `.btn-*`,
   `.badge-*`, `.empty-state*`, `.skeleton*`, `.confirm-*`) added to
   `styles.css` as the single source of truth for color/spacing/type.
3. **`626fd22`** — App shell polish: mobile sidebar drawer, provisioning
   form validation, copy/jargon cleanup.
4. **`153bb47`** — Executive Dashboard: real volume KPI wiring, consistent
   ₹ (INR) formatting via `formatINR()`, table-based anomaly feed.
   (This step's slate→stone migration was later discovered incomplete;
   finished as part of Step 9's commit, see below.)
5. **`75c09c1`** — Ledger Data Center restyle to design tokens.
6. **`57a2910`** — Anomaly & Fraud Lab restyle to design tokens.
   (`19c6f5b` — follow-up fix: restored a missing LLM-enrichment button.)
7. **`0937b0b`** — 3-Way Reconciliation restyle to design tokens.
8. **`e82deae`** — Policy RAG Copilot restyle to design tokens.
9. **`f49c3b4`** — Working Paper Report restyle to design tokens; also
   fixed leftover `slate-` instances in the Overview panel missed in
   Step 4.
10. **`cb5c78e`** — About/Runbook page restyle to design tokens.
11. **`edd7ab2`** — Responsive & accessibility polish:
    - Finished the slate→stone migration in `index.html`'s app shell
      (body, vendor-picker modal, content area, header bar) — the last
      remaining light-mode surfaces still on the old palette.
    - Fixed a stray `text-slate-200` icon color in `toast.js`'s info
      variant to match its stone-based container.
    - Added `aria-label` to every icon-only control that lacked an
      accessible name (sidebar toggle, AI Copilot header button, logout,
      vendor-picker back button, datacenter refresh/clear-search, drawer
      close, toast dismiss).
    - Added `role="dialog"` + `aria-modal` + `aria-label` to the
      vendor-picker overlay, `aria-label="Primary navigation"` to the
      sidebar, and `role="status"` + `aria-live="polite"` to the toast
      container.
    - Confirmed (no change needed): global `focus-visible` styles,
      Modal/ConfirmDialog focus-trap + Escape-to-close behavior, and
      existing responsive breakpoints (sidebar collapse → off-canvas
      drawer on tablet/mobile) were already correctly in place from
      earlier steps.
12. **Final QA** (this step) — full-repo grep sweep, diff review, changelog.

## Intentional exceptions (not bugs)

- **Dark sidebar (`<aside>`) retains `slate-` classes** (4 instances:
  header border, Copilot mini-banner background/border/text, footer
  copyright text). The sidebar has its own hardcoded navy-gradient CSS
  background (`aside { background: linear-gradient(180deg, #090d16 0%,
  #0f172a 100%); }` in `styles.css`), independent of Tailwind's stone/slate
  utility system. Slate is the visually correct (cool-toned) choice against
  that navy backdrop — converting it to warm-toned stone would create a
  mismatch, not fix one.
- **Overview's risk-trend chart uses mock/illustrative data** — this was a
  pre-existing product decision (documented in-code at `overview.js` lines
  115-117), not introduced by this pass. Only its presentation (styling,
  axes, legend, tooltip, colors) was restyled; the underlying series was
  left untouched per the "no logic/data changes" rule.
- **Brand accent stayed amber/gold** — a deliberate decision made early in
  this project, not remapped to indigo/blue. `--status-indigo` remains in
  the token system for its existing non-brand semantic use only.

## Known minor gap (not addressed)

- `#vendor-switcher-wrap`'s `<select>` uses an inline SVG chevron with a
  raw hex color (`%2364748b`, slate-500's hex equivalent) baked into a
  `background-image` data URI in `styles.css`. This wasn't caught by the
  `slate-` class-name grep sweep since it's a hex value, not a Tailwind
  utility class. It's a decorative dropdown arrow, not a named/visible
  inconsistency — left as-is, flagged here for anyone doing a future
  full-token-purity pass.

## Testing method (please read before relying on "done")

Each step was verified by: re-running the grep sweep for stale classes,
reviewing the full `git diff`, and curl-checking affected routes against
the local dev server (`localhost:8000`) to confirm 200 responses and no
broken asset paths. **Live interactive browser/console testing (clicking
through flows, watching Network/Console tabs in a real browser) was NOT
performed during this session** — only static code review and HTTP-level
checks were used as a substitute. Before shipping, do a manual pass through
each view in a browser to confirm pixel-level appearance and interaction
behavior, especially: vendor picker modal open/close, sidebar drawer on a
narrow viewport, toast stacking/dismissal, and the reconciliation/anomaly
inspector drawers.

## Recommended backend changes (not implemented)

None identified. No visual improvement encountered during this pass
required a backend/API/data-shape change; everything achievable within the
frontend-only constraint was implemented directly.
