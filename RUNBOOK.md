# RUNBOOK — running & exercising the AI Auditor Assistant

A step-by-step check that every module works. Assumes you are in `d:\ML\ai-auditor-assistant`.

## 1. One-time setup

```bash
pip install -r requirements.txt
copy .env.example .env          # then edit .env — see below
python -m backend.ml.train_anomaly_model
```

`.env` essentials:

| key | needed for |
|---|---|
| `GEMINI_API_KEY` | LLM reason codes, invoice OCR, RAG answers, report narrative. **Everything still runs without it** — each feature has a deterministic fallback. |
| `JWT_SECRET_KEY` | stable login sessions across restarts (any 64-hex string) |

Optional but recommended: `pip install sentence-transformers` — without it the RAG engine
falls back to ChromaDB's built-in embeddings (lower retrieval quality, still works).

## 2. Start it

```bash
python run.py
```

- Dashboard: <http://127.0.0.1:8000>
- API explorer (Swagger): <http://127.0.0.1:8000/docs>

Startup log should show `[STARTUP] Anomaly IsolationForest model loaded.` and
`[RAG ENGINE] Successfully ingested N chunks`.

## 3. Sign in

There are **no passwords**. On the sign-in screen pick one:

- **All Vendors (Global)** — the whole ledger. Use this for the anomaly / overview demo.
- **An existing vendor** (e.g. `VND-1001`) — scopes every screen to that vendor.
- **+ Add New Vendor** — provisions a fresh, empty vendor.

Switch context any time from the dropdown in the top bar.

## 4. Walk through the six views

| View | What to do | What "working" looks like |
|---|---|---|
| **Overview** | loads automatically | KPI tiles populate (audited ≈ 185,806), department risk + trend charts render, activity stream lists recent flags |
| **Data Center** | browse / search the ledger; paginate | grid shows real rows (vendor, department, **non-zero `amount`**, date). Search by vendor or PO number filters live |
| **Anomaly Engine** | click **Run Detection**; drag the risk slider; click a row | ~800 critical / ~15k medium flagged; scatter plot renders; clicking a row opens the SHAP drawer with per-feature bars + a plain-English reason code |
| **Policy RAG** | ask e.g. *"What is the approval threshold for large expenses?"* | returns an answer grounded in the policy PDFs with document + page citations |
| **3-Way Recon** | pick a **specific vendor** (not "All"), upload PDFs from `data/sample_invoices/` | each invoice is parsed (vendor, number, total) and matched / flagged against the ledger (see note below) |
| **Report** | click **Generate Working Paper** | downloads a multi-page PDF: executive summary, risk table, reconciliation findings, sign-off lines |

## 5. Quick API smoke test (no browser)

```bash
B=http://127.0.0.1:8000
TOKEN=$(curl -s -X POST $B/api/auth/login -H "Content-Type: application/json" -d '{}' \
        | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
H="Authorization: Bearer $TOKEN"

curl -s $B/api/health
curl -s "$B/api/ledger?page=1&limit=3"          -H "$H" -H "X-Vendor-Context: ALL"
curl -s -X POST "$B/api/audit/anomalies?min_risk_score=75" -H "$H" -H "X-Vendor-Context: ALL"
curl -s -X POST $B/api/rag/query -H "$H" -H "Content-Type: application/json" \
     -d '{"query":"approval threshold for large expenses","top_k":2}'
curl -s -X POST $B/api/report/generate -H "$H" -d '{}' -o report.pdf
curl -s -X POST $B/api/recon/upload -H "$H" -H "X-Vendor-Context: VND-1001" \
     -F "invoices=@data/sample_invoices/INV-2026-001.pdf"
```

## 6. Retrain / re-evaluate the anomaly model

```bash
python -m backend.ml.train_anomaly_model --trees 200 --contamination 0.03
python -m backend.ml.evaluate_anomaly_model
```

Restart the server (or it auto-reloads) to pick up a new model artifact.

## Known limitations (not bugs)

- **Gemini free tier is ~20 requests/day.** Once exhausted you'll see `429 RESOURCE_EXHAUSTED`
  in the log and features fall back to deterministic output (canned reason codes, regex
  invoice parsing, extractive RAG answers, templated report summary). Wait for the daily
  reset or use a paid key for the full LLM experience.
- **Sample invoices vs. ledger mismatch.** `data/sample_invoices/*.pdf` were authored for the
  original synthetic INR ledger; the bundled ledger is now the USD City-of-Chicago Contracts
  dataset. Reconciliation runs correctly but every sample invoice reports
  `UNRECORDED_INVOICE` because those vendors aren't in the Chicago data. To see MATCHED /
  AMOUNT_MISMATCH results, reconcile invoices whose vendor + amount exist in the ledger.
- **Currency symbols.** Parts of the SPA still render `₹` labels; the data is USD. Cosmetic
  only — set `CURRENCY_SYMBOL` in `.env` for the backend-generated text.
- **No transaction time in the ledger**, so the "off-hours" rule only catches weekend
  approval dates (hence its lighter weight).
