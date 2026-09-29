import os
import io
import sys
import site

# Ensure user site packages directory is included
user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

import numpy as np
import pandas as pd
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.config import settings
from backend.db import get_db, init_db
from backend.auth import (
    get_current_user, resolve_vendor_context,
    create_access_token, create_refresh_token,
    rotate_refresh_token, revoke_refresh_token,
)
from backend.schemas_auth import LoginRequest, TokenResponse, RefreshRequest, VendorCreateRequest, VendorOut
from backend.services import vendor_service
from backend.services.ocr_recon import perform_3way_reconciliation
from backend.services.anomaly_engine import run_anomaly_detection_pipeline
from backend.services.rag_engine import ingest_policy_pdfs, query_policy_rag, get_chroma_collection
from backend.services.report_generator import build_audit_working_paper_pdf
from backend.utils.data_generator import generate_synthetic_ledger, generate_sample_invoices, generate_policy_documents, seed_vendor_registry
from backend.utils.data_cleaner import load_and_preprocess_ledger

app = FastAPI(
    title="AI Auditor Assistant API",
    description="Enterprise Copilot for Financial Controls, 3-Way Invoice Reconciliation, Isolation Forest ML Anomaly Detection, and Policy Compliance RAG.",
    version="1.0.0"
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: narrowed to configured dev origins. Credentials aren't needed since auth
# travels via the Authorization header (JWT), not cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DB, vendor/user seed data, and synthetic demo data on startup if missing
@app.on_event("startup")
def startup_event():
    os.makedirs(settings.DATA_DIR, exist_ok=True)

    init_db()
    from backend.db import SessionLocal
    db = SessionLocal()
    try:
        seed_vendor_registry(db)
    finally:
        db.close()

    if not os.path.exists(settings.RAW_LEDGER_PATH):
        print("[STARTUP] Generating synthetic ledger, sample invoices, and corporate policies...")
        generate_synthetic_ledger()
        generate_sample_invoices()
        generate_policy_documents()

    # Warm (or train, on a fresh checkout) the anomaly model so the first
    # /api/audit/anomalies request isn't paying the fit cost.
    try:
        from backend.services.anomaly_engine import _get_model_bundle
        _get_model_bundle()
        print("[STARTUP] Anomaly IsolationForest model loaded.")
    except Exception as e:
        print(f"[STARTUP] Anomaly model warm-up skipped: {e}")

    try:
        # Idempotent — also refreshes chunk metadata (scope/vendor_id) on existing installs.
        ingest_policy_pdfs()
    except Exception as e:
        print(f"[STARTUP] ChromaDB auto-ingest note: {e}")

# ---------------------------------------------------------------------
# 1. SYSTEM HEALTH & METRICS
# ---------------------------------------------------------------------
@app.get("/api/health")
def get_health_status():
    return {
        "status": "ONLINE",
        "gemini_api_configured": bool(settings.GEMINI_API_KEY),
        "raw_ledger_exists": os.path.exists(settings.RAW_LEDGER_PATH),
        "vector_db_path": settings.CHROMA_DB_PATH
    }

# ---------------------------------------------------------------------
# AUTH & MULTI-TENANCY ENDPOINTS
# ---------------------------------------------------------------------
@app.post("/api/auth/login", response_model=TokenResponse)
@limiter.limit("20/minute")
def login(request: Request, req: LoginRequest, db: Session = Depends(get_db)):
    """
    Signing in means picking a vendor, not entering credentials:
    - vendor_id set: sign in to that existing vendor.
    - vendor_name set (no vendor_id): create the vendor, then sign in to it —
      it starts with a clean, empty dashboard.
    - neither set: sign in to the "All Vendors (Global)" aggregate view.
    """
    if req.vendor_id and req.vendor_id != "ALL":
        vendor = vendor_service.get_vendor_by_id(db, req.vendor_id)
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")
    elif req.vendor_name:
        vendor = vendor_service.create_vendor(db, req.vendor_name, req.department, req.category)
        # ensure 100 ledgers for vendors created via login flow as well
        try:
            from backend.utils.data_generator import ensure_vendor_ledgers
            ensure_vendor_ledgers(vendor.vendor_id, vendor.vendor_name, vendor.department, vendor.category, per_vendor=100)
        except Exception as e:
            print(f"[LOGIN VENDOR CREATE] ledger provision note: {e}")
    else:
        vendor = None

    access_token = create_access_token()
    refresh_token = create_refresh_token(db)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        vendor_id=vendor.vendor_id if vendor else "ALL",
        vendor_name=vendor.vendor_name if vendor else None,
    )

@app.post("/api/auth/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    new_access, new_refresh = rotate_refresh_token(db, req.refresh_token)
    # The vendor being worked on is a client-side session choice (X-Vendor-Context),
    # not something tied to the token — refresh doesn't need to know it.
    return TokenResponse(access_token=new_access, refresh_token=new_refresh, vendor_id="ALL")

@app.post("/api/auth/logout")
def logout(req: RefreshRequest, db: Session = Depends(get_db)):
    revoke_refresh_token(db, req.refresh_token)
    return {"status": "SUCCESS"}

@app.get("/api/auth/me")
def get_me(user=Depends(get_current_user)):
    return {"username": user.username}

@app.get("/api/public/vendors", response_model=List[VendorOut])
def list_public_vendors(db: Session = Depends(get_db)):
    """Populates the sign-in vendor picker ('which vendor are you working on?')."""
    return vendor_service.list_vendors(db)

@app.post("/api/auditors/vendors/create", response_model=VendorOut)
def create_vendor_endpoint(
    req: VendorCreateRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    vendor = vendor_service.create_vendor(
        db, req.vendor_name, req.department, req.category, created_by=user.username
    )
    # Auto-provision exactly 100 ledger rows for the new vendor so Data Center is never empty
    try:
        from backend.utils.data_generator import ensure_vendor_ledgers
        ensure_vendor_ledgers(vendor.vendor_id, vendor.vendor_name, vendor.department, vendor.category, per_vendor=100)
    except Exception as e:
        print(f"[VENDOR CREATE] ledger auto-provision note for {vendor.vendor_id}: {e}")
    return vendor

# ---------------------------------------------------------------------
# 2. MODULE 1: 3-WAY RECONCILIATION ENDPOINTS
# ---------------------------------------------------------------------
@app.post("/api/recon/upload")
async def reconcile_invoices(
    invoices: List[UploadFile] = File(...),
    ledger_file: Optional[UploadFile] = File(None),
    user=Depends(get_current_user),
    vendor_id: str = Depends(resolve_vendor_context)
):
    """
    Accepts PDF invoice files + optional CSV ledger. Parses PDFs via Gemini 2.5 Flash
    and performs 3-way reconciliation against CSV ledger.
    """
    if vendor_id == "ALL":
        raise HTTPException(status_code=400, detail="Select a specific vendor to run reconciliation — 'All Vendors' is not supported for this action.")
    try:
        # Load ledger DataFrame
        if ledger_file:
            content = await ledger_file.read()
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = load_and_preprocess_ledger(vendor_id=vendor_id)

        pdf_tuples = []
        for inv in invoices:
            content = await inv.read()
            pdf_tuples.append((inv.filename, content))

        results = perform_3way_reconciliation(pdf_tuples, df, vendor_id=vendor_id)

        matched_count = len([r for r in results if r['status'] == 'MATCHED'])
        mismatch_count = len([r for r in results if r['status'] == 'AMOUNT_MISMATCH'])
        unrecorded_count = len([r for r in results if r['status'] == 'UNRECORDED_INVOICE'])
        
        return {
            "status": "SUCCESS",
            "summary": {
                "total_invoices_processed": len(results),
                "matched_count": matched_count,
                "amount_mismatch_count": mismatch_count,
                "unrecorded_invoice_count": unrecorded_count
            },
            "reconciliation_results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reconciliation error: {str(e)}")

# ---------------------------------------------------------------------
# 3. MODULE 2: ANOMALY DETECTION ENDPOINTS
# ---------------------------------------------------------------------
@app.post("/api/audit/anomalies")
async def detect_anomalies(
    min_risk_score: float = Query(0.0, ge=0.0, le=100.0),
    use_llm: bool = Query(False),
    user=Depends(get_current_user),
    vendor_id: str = Depends(resolve_vendor_context)
):
    """
    Runs Isolation Forest ML + Deterministic Rules + SHAP on the General Ledger.
    Set use_llm=true to also enrich the top-5 anomalies with Gemini AI explanations
    (adds ~5-10s; default is off so the dashboard loads fast).
    Offloaded to a thread so ML computation doesn't block the event loop.
    """
    try:
        pipeline_results = await run_in_threadpool(
            run_anomaly_detection_pipeline,
            min_risk_score=min_risk_score,
            vendor_id=vendor_id,
            use_llm=use_llm
        )
        return {
            "status": "SUCCESS",
            **pipeline_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Anomaly detection error: {str(e)}")

# ---------------------------------------------------------------------
# 4. MODULE 3: POLICY RAG ASSISTANT ENDPOINTS
# ---------------------------------------------------------------------
class RAGQueryRequest(BaseModel):
    query: str
    top_k: Optional[int] = 3

@app.post("/api/rag/query")
def query_policy_assistant(
    req: RAGQueryRequest,
    user=Depends(get_current_user),
    vendor_id: str = Depends(resolve_vendor_context)
):
    """Ledger-grounded + policy-grounded financial copilot. Rejects non-financial chatter, cites ledger Txn IDs & policy pages."""
    try:
        res = query_policy_rag(user_query=req.query, top_k=req.top_k or 3, vendor_id=vendor_id)
        return {
            "status": "SUCCESS",
            "query": req.query,
            "answer": res["answer"],
            "citations": res.get("citations", []),
            "ledger_citations": res.get("ledger_chunks", []),
            "policy_citations": res.get("retrieved_chunks", []),
            "is_financial": res.get("is_financial", True),
            "vendor_scope": res.get("vendor_scope", vendor_id),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query error: {str(e)}")

@app.get("/api/rag/documents")
def list_ingested_policy_documents(user=Depends(get_current_user)):
    """Lists all policy documents ingested into ChromaDB."""
    try:
        col = get_chroma_collection()
        count = col.count()
        pdf_files = [f for f in os.listdir(settings.POLICY_DIR) if f.endswith('.pdf')] if os.path.exists(settings.POLICY_DIR) else []
        return {
            "status": "SUCCESS",
            "total_vector_chunks": count,
            "policy_files": pdf_files
        }
    except Exception as e:
        return {"status": "ERROR", "detail": str(e)}

@app.post("/api/rag/ingest")
def reingest_policies(user=Depends(get_current_user)):
    """Triggers re-indexing of policy PDFs into ChromaDB."""
    try:
        res = ingest_policy_pdfs()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Policy ingestion error: {str(e)}")

# ---------------------------------------------------------------------
# 5. MODULE 4: WORKING PAPER PDF REPORT ENDPOINT
# ---------------------------------------------------------------------
class ReportRequest(BaseModel):
    summary: Optional[Dict[str, Any]] = None
    reconciliation_findings: Optional[List[Dict[str, Any]]] = None
    anomalies: Optional[List[Dict[str, Any]]] = None
    auditor_notes: Optional[str] = "All flagged split transactions and unrecorded invoices must be resolved prior to period close."

@app.post("/api/report/generate")
@app.post("/api/report/export")
def generate_report(
    req: ReportRequest,
    user=Depends(get_current_user),
    vendor_id: str = Depends(resolve_vendor_context)
):
    """Compiles findings into ReportLab PDF and streams binary response."""
    try:
        # If payload is empty, generate baseline summary automatically
        audit_data = req.dict()
        if not audit_data.get('anomalies'):
            anomaly_res = run_anomaly_detection_pipeline(min_risk_score=50.0, vendor_id=vendor_id)
            audit_data['summary'] = anomaly_res['summary']
            audit_data['anomalies'] = anomaly_res['anomalies']

        pdf_bytes = build_audit_working_paper_pdf(audit_data)
        
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=Audit_Working_Paper_Report.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation error: {str(e)}")


# ---------------------------------------------------------------------
# 6. LEDGER MANAGEMENT & ANOMALY INJECTOR ENDPOINTS
# ---------------------------------------------------------------------
@app.get("/api/ledger")
def get_ledger_data(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    category: Optional[str] = None,
    sort_by: Optional[str] = Query(None, description="Column to sort by: date, amount, vendor_name, transaction_id"),
    sort_dir: Optional[str] = Query("asc", description="asc or desc"),
    user=Depends(get_current_user),
    vendor_id: str = Depends(resolve_vendor_context)
):
    """Retrieves paginated General Ledger records — fully featured for Data Center.
    Supports search across all display fields, category filter, vendor scoping, and sorting.
    """
    try:
        df = load_and_preprocess_ledger(vendor_id=vendor_id)

        # — Search across all user-visible fields (amount as string too) —
        if search:
            search_clean = search.lower().strip()
            # include amount string, category, description variants
            search_cols = [c for c in [
                'vendor_name', 'vendor_id', 'transaction_id', 'department',
                'category', 'amount', 'description',
                'Purchase Order Description', 'Contract Type', 'approval_status'
            ] if c in df.columns]
            # amount numeric search: also match formatted
            mask = pd.Series(False, index=df.index)
            for col in search_cols:
                mask = mask | df[col].astype(str).str.lower().str.contains(search_clean, regex=False, na=False)
            df = df[mask]

        if category and category != "ALL" and 'category' in df.columns:
            df = df[df['category'].astype(str) == category]

        # — Sorting —
        valid_sort = {"date", "amount", "vendor_name", "transaction_id", "department", "category", "time"}
        if sort_by and sort_by in valid_sort and sort_by in df.columns:
            ascending = (sort_dir or "asc").lower() != "desc"
            # date column is datetime inside this df — sort before str conversion
            try:
                df = df.sort_values(by=sort_by, ascending=ascending, kind="mergesort")
            except Exception:
                pass
        else:
            # default: newest date first? Keep chronological ascending for stable pagination
            if "date" in df.columns:
                df = df.sort_values(by=["date", "time"], ascending=[True, True])

        total_records = len(df)
        total_pages = (total_records + limit - 1) // limit if total_records > 0 else 0
        # clamp page
        page = max(1, min(page, total_pages if total_pages > 0 else 1))
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        sliced_df = df.iloc[start_idx:end_idx].copy()

        # Sanitize NaNs for JSON compliance
        sliced_df = sliced_df.replace({np.nan: None})

        records = sliced_df.to_dict(orient="records")
        for r in records:
            updated = {}
            for k, v in r.items():
                if hasattr(v, 'strftime'):
                    updated[k] = v.strftime('%Y-%m-%d')
                elif pd.isna(v):
                    updated[k] = None
                elif isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                    updated[k] = None
                else:
                    updated[k] = v
            # ensure defaults for frontend convenience
            if "category" not in updated or not updated["category"]:
                updated["category"] = r.get("category") or "General"
            if "is_injected_anomaly" not in updated:
                updated["is_injected_anomaly"] = False
            if "anomaly_type" not in updated:
                updated["anomaly_type"] = "NONE"
            if "description" not in updated or not updated["description"]:
                updated["description"] = updated.get("Purchase Order Description") or f"Procurement for {updated.get('category','General')}"
            r.clear()
            r.update(updated)

        # aggregate category breakdown for filter UI
        categories = sorted(df["category"].astype(str).unique().tolist()) if "category" in df.columns else []

        return {
            "status": "SUCCESS",
            "page": page,
            "limit": limit,
            "total_records": total_records,
            "total_pages": total_pages,
            "categories": categories,
            "vendor_scope": vendor_id,
            "records": records
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ledger fetch error: {str(e)}")


@app.get("/api/ledger/stats")
def get_ledger_stats(
    user=Depends(get_current_user),
    vendor_id: str = Depends(resolve_vendor_context)
):
    """Quick stats for the Data Center header cards."""
    try:
        df = load_and_preprocess_ledger(vendor_id=vendor_id)
        total = len(df)
        anomalies = int(df["is_injected_anomaly"].sum()) if "is_injected_anomaly" in df.columns else 0
        total_amt = float(df["amount"].sum()) if "amount" in df.columns and total > 0 else 0.0
        categories = sorted(df["category"].astype(str).unique().tolist()) if "category" in df.columns else []
        # per-vendor counts (when ALL scope)
        vendor_counts = {}
        if vendor_id == "ALL" and "vendor_id" in df.columns:
            vendor_counts = df["vendor_id"].value_counts().to_dict()
        return {
            "status": "SUCCESS",
            "vendor_scope": vendor_id,
            "total_records": total,
            "anomaly_records": anomalies,
            "total_amount": total_amt,
            "categories": categories,
            "vendor_counts": vendor_counts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ledger stats error: {str(e)}")


@app.post("/api/ledger/inject-anomalies")
def trigger_synthetic_injection(
    count: int = Query(None, description="Total rows to regenerate; if omitted creates 100 per vendor"),
    per_vendor: int = Query(100, ge=10, le=500, description="Rows per vendor when count omitted"),
    user=Depends(get_current_user)
):
    """Regenerates corporate_ledger.csv with exactly `per_vendor` rows per vendor (default 100)."""
    try:
        # Default contract: 100 per vendor × current vendor count
        if count is not None:
            file_path = generate_synthetic_ledger(count=count)
            total = count
            msg = f"Regenerated {total} transactions ({total // 10 if total else 0}/vendor approx) with embedded anomaly patterns."
        else:
            file_path = generate_synthetic_ledger(per_vendor=per_vendor)
            # count actual vendors
            from backend.utils.data_generator import _resolve_vendor_list as _rv
            vendors = _rv()
            total = len(vendors) * per_vendor
            msg = f"Regenerated {total} transactions — exactly {per_vendor} per vendor × {len(vendors)} vendors. Balanced anomaly injection included."
        return {
            "status": "SUCCESS",
            "message": msg,
            "file_path": file_path,
            "total_records": total,
            "per_vendor": per_vendor,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Injection error: {str(e)}")

# Mount Data Directory for sample PDFs
if os.path.exists(settings.DATA_DIR):
    app.mount("/data", StaticFiles(directory=settings.DATA_DIR), name="data")

# Mount Frontend Static Directory
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

