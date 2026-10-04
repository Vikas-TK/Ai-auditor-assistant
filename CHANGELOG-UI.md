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

## Testing method

Each step was verified by: re-running the grep sweep for stale classes,
reviewing the full `git diff`, and curl-checking affected routes against
the local dev server (`localhost:8000`).

**End-to-end scripted API verification (added in a follow-up pass):** no
browser-automation tool was available in this environment, so true
click-through/DevTools testing could not be performed. As the closest
practical substitute, every endpoint the frontend calls was exercised
directly against the running dev server, following the real frontend flow
(login → token → vendor-scoped calls):

- `GET /api/health` → 200
- `GET /api/public/vendors` → 200, vendor list returned
- `POST /api/auth/login` (vendor_id from the list above) → 200, access/refresh tokens issued
- `GET /api/auth/me` (bearer token) → 200
- `GET /api/ledger?page=1&limit=5` (bearer + `X-Vendor-Context`) → 200, paginated records
- `GET /api/ledger/stats` → 200
- `POST /api/audit/anomalies?min_risk_score=50` → 200, risk-scored anomalies returned
- `POST /api/rag/query` → 200, grounded answer with citations
- `POST /api/report/generate` → 200, valid PDF stream (`%PDF` magic bytes, non-trivial size)
- All 17 static asset routes referenced by `index.html` (`styles.css`, every `js/views/*.js`, `js/components/*.js`, `js/utils/format.js`, `about.html`) → 200
- Cross-checked every `apiFetch(...)` call site in `frontend/js/api.js` against the backend's route table in `main.py` — all match exactly; no endpoint drift introduced by this pass.

**Follow-up pass** — exercised the remaining non-destructive endpoints that
were initially deferred:

- `POST /api/auth/refresh` → 200, new access/refresh token pair issued
- `POST /api/auth/logout` → 200, `{"status":"SUCCESS"}`
- `POST /api/recon/upload` (real sample PDFs from `data/sample_invoices/`) →
  200; Gemini PDF extraction, vendor fuzzy-matching, and amount-variance
  detection all returned correctly structured results (one
  `AMOUNT_MISMATCH`, one `UNRECORDED_INVOICE`)

Deliberately still **not** exercised: `POST /api/auditors/vendors/create`
and `POST /api/ledger/inject-anomalies` — both mutate persistent data
(create a vendor record / inject anomalies into the ledger), and a
verification pass shouldn't leave side effects in shared data as its own
side effect. Their request/response wiring was already confirmed by the
static `apiFetch()` cross-check above; only the live mutation was skipped.

This confirms no route, auth flow, or static asset was broken by the UI
changes. It does **not** substitute for a human visually confirming
pixel-level appearance and interaction polish (modal open/close animation,
sidebar drawer on a narrow viewport, toast stacking, drawer focus behavior)
in an actual browser — that manual pass is still recommended before
considering this fully shipped.

## Recommended backend changes (not implemented)

- **`GET /api/rag/documents` throws a caught exception** and returns
  `{"status":"ERROR","detail":"'Chroma' object has no attribute 'count'"}`
  (HTTP 200, error embedded in the body). Root cause is a ChromaDB
  client/API version mismatch in `get_chroma_collection()` inside
  `backend/services/rag_engine.py` — pre-existing, unrelated to this UI
  pass, and not touched since it's backend/service logic. **Not a visible
  break**: `rag.js`'s `loadKnowledgeBaseStats()` already guards for a
  missing `policy_files`/`total_vector_chunks` and falls back to
  placeholder values (`2` docs, `12` chunks), so the Policy Copilot panel
  still renders correctly — it just silently shows stale placeholder counts
  instead of the real ChromaDB totals. Recommended fix: update
  `get_chroma_collection()`/the `count()` call to match the installed
  `chromadb` client API.
