# AI-Powered Internal Auditor Assistant (Fintech & Corporate Finance Copilot)

An automated copilot for internal financial auditors, risk managers, and compliance teams. Automates multi-document matching, performs semantic search over corporate policy PDFs using RAG, detects general ledger anomalies with Isolation Forest ML & SHAP explainability, and auto-generates structured audit working papers in PDF format.

---

## 🌟 Key Features
- **Module 1: 3-Way Reconciliation Engine**: PDF Invoice OCR (Gemini 2.5 Flash / `pdfplumber`) + Fuzzy String Matching (`rapidfuzz`) against CSV General Ledger.
- **Module 2: Unsupervised Anomaly Engine**: Deterministic rule checks (split payments just under a round approval limit, weekend/off-hours entries, short-window duplicate payments — all thresholds configurable) + a **pre-trained** Scikit-Learn Isolation Forest scoring rows 0–100 (`risk >= 50` = the model's own contamination cut) + SHAP explainability & Gemini LLM reason codes. Training/eval live in [`backend/ml/`](backend/ml/README.md).
- **Module 3: Policy Compliance RAG Engine**: ChromaDB Vector Store + SentenceTransformers + Gemini 2.5 Flash for natural language policy QA with exact page citations.
- **Module 4: Working Paper & Report Generator**: Python ReportLab PDF compilation with executive summaries, risk tables, and auditor sign-off lines.
- **FinTech Dark Mode SPA Dashboard**: Built with Vanilla JS, Tailwind CSS CDN, Chart.js risk heatmaps, side-drawer inspectors, and interactive citation popups across 6 dedicated views.

---

## 🚀 Quick Start Guide

### 1. Requirements & Setup
Ensure Python 3.10+ is installed.

```bash
cd d:\ML\ai-auditor-assistant
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and insert your Gemini API Key:
```env
GEMINI_API_KEY=your_gemini_api_key_here
PORT=8000
HOST=127.0.0.1
```
`.env.example` also documents the Module 2 rule-engine knobs
(`ANOMALY_APPROVAL_THRESHOLDS`, `ANOMALY_DUP_MIN_AMOUNT`, `CURRENCY_SYMBOL`, …) — the
defaults suit the bundled USD dataset; retune them for another ledger.

### 3. Train the Anomaly Model (one-time)
```bash
python -m backend.ml.train_anomaly_model
```
Fits the Isolation Forest on the general ledger and saves it to `data/models/`. Optional —
the server auto-trains on first use — but running it explicitly lets you set params and
verifies the data pipeline. See [backend/ml/README.md](backend/ml/README.md).

### 4. Run the Development Server
```bash
python run.py
```
Open your browser and navigate to:
- **Web SPA Dashboard**: `http://127.0.0.1:8000`
- **FastAPI Interactive API Docs**: `http://127.0.0.1:8000/docs`

> New here? [RUNBOOK.md](RUNBOOK.md) walks through signing in and exercising every module,
> plus known limitations (Gemini free-tier quota, sample-invoice/ledger mismatch).

---

## 📂 Project Structure
```text
ai-auditor-assistant/
├── .env
├── .env.example
├── ARCHITECTURE.md
├── requirements.txt
├── README.md
├── run.py                       # Single-command server & setup script
│
├── data/                        # Local Test Datasets & Storage
│   ├── raw_ledgers/             # corporate_ledger.csv (City of Chicago Contracts) + cleaned_ledger.csv
│   ├── models/                  # Trained anomaly model artifact (gitignored, regenerable)
│   ├── sample_invoices/         # Generated vendor PDF receipts
│   ├── policy_documents/        # Corporate Policy PDFs
│   └── vector_db/               # Persistent ChromaDB vector database
│
├── backend/                     # FastAPI Core Backend
│   ├── main.py                  # App entry point & routes
│   ├── config.py                # Environment & settings loader (+ anomaly rule knobs)
│   ├── services/
│   │   ├── ocr_recon.py         # Gemini OCR + rapidfuzz 3-Way Match engine
│   │   ├── anomaly_engine.py    # Rule checks + persisted Isolation Forest + SHAP + Gemini Explainer
│   │   ├── rag_engine.py        # ChromaDB Vector Store + Gemini 2.5 Flash RAG
│   │   └── report_generator.py  # ReportLab PDF working paper generator
│   ├── ml/                      # Offline ML: feature builder, training & evaluation (see ml/README.md)
│   │   ├── features.py          # build_feature_frame() — shared by training & serving
│   │   ├── train_anomaly_model.py
│   │   ├── evaluate_anomaly_model.py
│   │   └── artifact.py          # model bundle load/save + risk-score mapping
│   └── utils/
│       ├── data_cleaner.py      # Data preprocessing & feature engineering
│       ├── data_generator.py    # Synthetic ledger, invoice & policy generators
│       └── helpers.py           # Currency & date formatting helpers
│
└── frontend/                    # Vanilla HTML5/CSS3/JS Dark-Mode FinTech SPA
    ├── index.html               # Single Page Application layout
    ├── css/
    │   └── styles.css           # FinTech dark theme design system
    └── js/
        ├── app.js               # Router, state store & tab switching
        ├── api.js               # Fetch API client
        ├── components/          # Drawers, modals, toast, table helper
        └── views/               # 6 Page controllers (overview, recon, anomaly, rag, datacenter, report)
```
