# ARCHITECTURE.md - AI Auditor Assistant System Architecture

## Overview & System Philosophy
The AI Auditor Assistant is built on a **HYBRID ARCHITECTURE**:
- **Deterministic Math & Rules**: Python, Pandas, RapidFuzz, and Scikit-Learn handle 100% exact math matching, threshold validation, and Isolation Forest ML anomaly scoring.
- **Generative AI & Reasoning**: Google Gemini API (`gemini-2.5-flash`) handles zero-shot PDF invoice OCR parsing into Pydantic schemas, translating SHAP feature weights into plain-English auditor explanations, policy RAG question answering, and executive report synthesis.

```
                         ┌───────────────────────────────────────────────┐
                         │               FRONTEND SPA                    │
                         │  Vanilla HTML5 + Tailwind CSS + Chart.js      │
                         └──────────────────────┬────────────────────────┘
                                                │ REST API (JSON / Multipart)
                                                ▼
                         ┌───────────────────────────────────────────────┐
                         │              FASTAPI BACKEND                  │
                         └──────┬──────────────┬──────────────┬──────────┘
                                │              │              │
      ┌─────────────────────────┴─┐   ┌────────┴─────────┐  ┌─┴────────────────────────┐
      │ Module 1: 3-Way Recon     │   │ Module 2: Anomaly│  │ Module 3: Policy RAG   │
      │ • pdfplumber / Gemini OCR │   │ • IsolationForest│  │ • ChromaDB Vector DB   │
      │ • rapidfuzz Vendor Match  │   │ • Rule Checks    │  │ • SentenceTransformers │
      │ • Float Amount Match      │   │ • SHAP + Gemini  │  │ • Gemini 2.5 Flash RAG │
      └───────────────────────────┘   └──────────────────┘  └────────────────────────┘
                                                │
                                                ▼
                                 ┌──────────────────────────────┐
                                 │ Module 4: Working Paper PDF  │
                                 │ • ReportLab PDF Compilation  │
                                 │ • Stream Binary Download     │
                                 └──────────────────────────────┘
```

## Core Backend Modules
1. **ocr_recon.py**: Performs zero-shot invoice metadata extraction using Gemini 2.5 Flash (`response_schema`), fuzzy vendor string matching (`rapidfuzz`), and exact amount reconciliation against CSV General Ledger.
2. **anomaly_engine.py**: Evaluates deterministic rules (split transactions near the approval threshold, off-hours entries, duplicate payments) + scores rows with a **pre-trained Isolation Forest** loaded from `data/models/anomaly_iforest.joblib` (trained offline via `backend/ml/train_anomaly_model.py`, evaluated via `backend/ml/evaluate_anomaly_model.py`) + calculates SHAP feature weights + translates weights into 1-sentence plain-English reason codes using Gemini API.
3. **rag_engine.py**: Chunks policy PDFs using `pypdf`, embeds chunks using `sentence-transformers/all-MiniLM-L6-v2`, stores vectors in ChromaDB (`./data/vector_db`), and runs RAG queries with Gemini 2.5 Flash featuring document and page number citations.
4. **report_generator.py**: Compiles audit observations, high-risk anomalies, reconciliation variances, policy logs, and Gemini executive summaries into printable PDF working papers using ReportLab.
