import os
import json
import pdfplumber
import pandas as pd
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from backend.config import settings
from backend.utils.helpers import clean_vendor_name

# Define Pydantic Schema for Gemini Structured PDF Parsing
class InvoiceSchema(BaseModel):
    vendor_name: str = Field(description="Name of the selling vendor or merchant")
    invoice_number: str = Field(description="Unique invoice or bill number")
    date: str = Field(description="Invoice date in YYYY-MM-DD format")
    total_amount: float = Field(description="Grand total invoice amount including taxes")
    tax_amount: float = Field(description="Total tax amount if present, else 0.0")

class ReconciliationResult(BaseModel):
    invoice_filename: str
    vendor_name_extracted: str
    invoice_number_extracted: str
    pdf_amount: float
    matched_ledger_id: Optional[str] = None
    ledger_vendor_name: Optional[str] = None
    ledger_amount: Optional[float] = None
    variance_amount: float = 0.0
    status: str # MATCHED, AMOUNT_MISMATCH, UNRECORDED_INVOICE, DUPLICATE_INVOICE
    match_confidence: float = 0.0
    notes: str

def parse_pdf_with_gemini(pdf_bytes: bytes, filename: str) -> InvoiceSchema:
    """Uses Gemini 2.5 Flash API with response_schema for zero-shot structured extraction."""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is missing")

    try:
        from google.genai import types
        from backend.utils.helpers import get_gemini_client

        client = get_gemini_client()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type='application/pdf'),
                "Extract structured invoice metadata. Ensure total_amount and tax_amount are numeric floats."
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=InvoiceSchema,
                temperature=0.1
            )
        )
        if response.parsed:
            return response.parsed
        else:
            # Fallback to json loads if parsed is dict
            data = json.loads(response.text)
            return InvoiceSchema(**data)
    except Exception as e:
        print(f"[RECON Gemini Fallback] Failed Gemini extraction for {filename}: {str(e)}")
        # Fallback to pdfplumber regex extraction
        return parse_pdf_fallback(pdf_bytes, filename)

def parse_pdf_fallback(pdf_bytes: bytes, filename: str) -> InvoiceSchema:
    """Fallback text parsing using pdfplumber regex when API is offline."""
    import io, re
    text = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text += (page.extract_text() or "") + "\n"

    # Regex extraction
    inv_num_match = re.search(r'INVOICE:\s*([A-Z0-9\-]+)', text, re.IGNORECASE) or re.search(r'Invoice\s*#:\s*([A-Z0-9\-]+)', text)
    inv_num = inv_num_match.group(1) if inv_num_match else filename.replace(".pdf", "")

    vendor_match = re.search(r'Vendor:\s*([^\n]+)', text, re.IGNORECASE)
    vendor = vendor_match.group(1).strip() if vendor_match else "Unknown Vendor"
    # Invoice PDFs render "Vendor: X   Date: Y" on one line — keep only the vendor.
    vendor = re.split(r'\s{2,}|\s+(?:Date|GSTIN|Inv)\b', vendor, maxsplit=1, flags=re.IGNORECASE)[0].strip()

    _CUR = r'(?:Rs\.?|INR|₹|\$)?\s*'
    total_match = (re.search(rf'GRAND TOTAL:\s*{_CUR}([0-9,]+\.[0-9]{{2}})', text, re.IGNORECASE)
                   or re.search(rf'Total:\s*{_CUR}([0-9,]+\.[0-9]{{2}})', text, re.IGNORECASE))
    total = float(total_match.group(1).replace(",", "")) if total_match else 0.0

    tax_match = re.search(rf'(?:Tax|GST)[^:]*:\s*{_CUR}([0-9,]+\.[0-9]{{2}})', text, re.IGNORECASE)
    tax = float(tax_match.group(1).replace(",", "")) if tax_match else 0.0

    date_match = re.search(r'Date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})', text)
    date_str = date_match.group(1) if date_match else "2026-01-01"

    return InvoiceSchema(
        vendor_name=vendor,
        invoice_number=inv_num,
        date=date_str,
        total_amount=total,
        tax_amount=tax
    )

def perform_3way_reconciliation(invoice_files: List[tuple[str, bytes]], ledger_df: pd.DataFrame, vendor_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Reconciles uploaded PDF invoice bytes against CSV General Ledger DataFrame.
    Returns structured list of match results.

    `ledger_df` is expected to already be vendor-scoped by the caller (via
    load_and_preprocess_ledger(vendor_id=...)); `vendor_id` is accepted defensively
    to guard against a raw/unscoped DataFrame ever being passed in by mistake.
    """
    if vendor_id and vendor_id != "ALL" and "vendor_id" in ledger_df.columns:
        ledger_df = ledger_df[ledger_df["vendor_id"] == vendor_id]

    results = []
    seen_invoices = set()

    for filename, pdf_bytes in invoice_files:
        parsed_inv = parse_pdf_with_gemini(pdf_bytes, filename)
        
        # Check duplicate PDF upload
        if parsed_inv.invoice_number in seen_invoices:
            results.append({
                "invoice_filename": filename,
                "vendor_name_extracted": parsed_inv.vendor_name,
                "invoice_number_extracted": parsed_inv.invoice_number,
                "pdf_amount": parsed_inv.total_amount,
                "matched_ledger_id": "N/A",
                "ledger_vendor_name": "N/A",
                "ledger_amount": 0.0,
                "variance_amount": parsed_inv.total_amount,
                "status": "DUPLICATE_INVOICE",
                "match_confidence": 100.0,
                "notes": "Duplicate PDF invoice uploaded in single audit batch."
            })
            continue
        
        seen_invoices.add(parsed_inv.invoice_number)

        clean_pdf_vendor = clean_vendor_name(parsed_inv.vendor_name)
        
        # Candidate search in ledger
        best_match_row = None
        best_score = 0.0

        for idx, row in ledger_df.iterrows():
            clean_ledger_vendor = clean_vendor_name(str(row['vendor_name']))
            
            # Fuzzy match score
            vendor_similarity = fuzz.token_sort_ratio(clean_pdf_vendor, clean_ledger_vendor)
            
            # If vendor similarity is high (> 75%)
            if vendor_similarity > 75:
                amt_diff = abs(float(row['amount']) - parsed_inv.total_amount)
                # Exact amount match boosts confidence
                score = vendor_similarity + (30.0 if amt_diff < 0.01 else -20.0)
                
                if score > best_score:
                    best_score = score
                    best_match_row = row

        if best_match_row is not None and best_score > 60:
            ledger_amt = float(best_match_row['amount'])
            variance = round(parsed_inv.total_amount - ledger_amt, 2)
            
            if abs(variance) < 0.01:
                status = "MATCHED"
                notes = "3-Way Reconciliation successful. Vendor and amount match general ledger."
            else:
                status = "AMOUNT_MISMATCH"
                notes = f"Vendor matched but amount variance detected (₹{abs(variance):,.2f}). Invoice: ₹{parsed_inv.total_amount:,.2f} vs Ledger: ₹{ledger_amt:,.2f}."

            
            results.append({
                "invoice_filename": filename,
                "vendor_name_extracted": parsed_inv.vendor_name,
                "invoice_number_extracted": parsed_inv.invoice_number,
                "pdf_amount": parsed_inv.total_amount,
                "matched_ledger_id": str(best_match_row['transaction_id']),
                "ledger_vendor_name": str(best_match_row['vendor_name']),
                "ledger_amount": ledger_amt,
                "variance_amount": variance,
                "status": status,
                "match_confidence": min(100.0, round(best_score, 1)),
                "notes": notes
            })
        else:
            # Unrecorded Invoice
            results.append({
                "invoice_filename": filename,
                "vendor_name_extracted": parsed_inv.vendor_name,
                "invoice_number_extracted": parsed_inv.invoice_number,
                "pdf_amount": parsed_inv.total_amount,
                "matched_ledger_id": "UNRECORDED",
                "ledger_vendor_name": "N/A",
                "ledger_amount": 0.0,
                "variance_amount": parsed_inv.total_amount,
                "status": "UNRECORDED_INVOICE",
                "match_confidence": 0.0,
                "notes": "Unrecorded Invoice! No matching entry found in General Ledger."
            })

    return results
