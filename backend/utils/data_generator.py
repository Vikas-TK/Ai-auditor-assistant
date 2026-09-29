import os
import random
from datetime import datetime, timedelta
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
LEDGER_DIR = os.path.join(DATA_DIR, "raw_ledgers")
INVOICE_DIR = os.path.join(DATA_DIR, "sample_invoices")
POLICY_DIR = os.path.join(DATA_DIR, "policy_documents")

# Stable vendor_id registry — every synthetic vendor gets a fixed VND-#### id so
# ledger rows, invoices, and DB vendor records can all be tied together consistently.
VENDOR_REGISTRY = [
    {"vendor_id": "VND-1001", "vendor_name": "TechCorp Systems India Pvt Ltd", "department": "IT", "category": "Software & Hardware", "amount_range": (15000, 450000)},
    {"vendor_id": "VND-1002", "vendor_name": "Global Travel Logistics Mumbai", "department": "Travel", "category": "Flights & Hotels", "amount_range": (5000, 150000)},
    {"vendor_id": "VND-1003", "vendor_name": "Vertex Office Supplies Delhi", "department": "Operations", "category": "Office Supplies", "amount_range": (2000, 35000)},
    {"vendor_id": "VND-1004", "vendor_name": "Apex Marketing Agency Bengaluru", "department": "Marketing", "category": "Advertising & Media", "amount_range": (50000, 850000)},
    {"vendor_id": "VND-1005", "vendor_name": "Metro Cloud Hosting Hyderabad", "department": "IT", "category": "Cloud Infrastructure", "amount_range": (40000, 600000)},
    {"vendor_id": "VND-1006", "vendor_name": "Pinnacle Consulting India", "department": "Finance", "category": "Advisory Services", "amount_range": (75000, 1200000)},
    {"vendor_id": "VND-1007", "vendor_name": "CleanSpace Services Pvt Ltd", "department": "Operations", "category": "Facilities & Cleaning", "amount_range": (8000, 45000)},
    {"vendor_id": "VND-1008", "vendor_name": "Precision Logistics Chennai", "department": "Logistics", "category": "Freight & Shipping", "amount_range": (12000, 180000)},
    {"vendor_id": "VND-1009", "vendor_name": "Delta Catering & Hospitality", "department": "HR", "category": "Events & Catering", "amount_range": (5000, 55000)},
    {"vendor_id": "VND-1010", "vendor_name": "FastFleet Rentals India", "department": "Operations", "category": "Vehicle Rental", "amount_range": (8000, 75000)},
]

VENDOR_NAME_TO_ID = {v["vendor_name"]: v["vendor_id"] for v in VENDOR_REGISTRY}
# reverse map for quick lookup
VENDOR_MAP_BY_ID = {v["vendor_id"]: v for v in VENDOR_REGISTRY}


def seed_vendor_registry(db):
    """Idempotently upserts VENDOR_REGISTRY into the vendors SQL table."""
    from backend.models import Vendor

    existing_ids = {v.vendor_id for v in db.query(Vendor.vendor_id).all()}
    for entry in VENDOR_REGISTRY:
        if entry["vendor_id"] not in existing_ids:
            db.add(Vendor(
                vendor_id=entry["vendor_id"],
                vendor_name=entry["vendor_name"],
                department=entry["department"],
                category=entry["category"],
                is_seed_vendor=True,
            ))
    db.commit()


def ensure_directories():
    os.makedirs(LEDGER_DIR, exist_ok=True)
    os.makedirs(INVOICE_DIR, exist_ok=True)
    os.makedirs(POLICY_DIR, exist_ok=True)


def _resolve_vendor_list(vendor_override=None):
    """Return list of vendor dicts to generate ledgers for.
    Priority: explicit override > DB vendors (if DB exists and has rows) > VENDOR_REGISTRY
    """
    if vendor_override:
        return vendor_override
    # Try DB vendors
    try:
        from backend.db import SessionLocal
        from backend.models import Vendor
        if os.path.exists(os.path.join(DATA_DIR, "app.db")):
            db = SessionLocal()
            try:
                rows = db.query(Vendor).order_by(Vendor.vendor_id).all()
                if rows:
                    lst = []
                    for r in rows:
                        # Find amount_range from registry or default
                        base = VENDOR_MAP_BY_ID.get(r.vendor_id)
                        if base:
                            amount_range = base["amount_range"]
                        else:
                            # default range for custom vendors — infer from category or fallback
                            amount_range = (8000, 250000)
                        lst.append({
                            "vendor_id": r.vendor_id,
                            "vendor_name": r.vendor_name,
                            "department": r.department or (base["department"] if base else "General"),
                            "category": r.category or (base["category"] if base else "General"),
                            "amount_range": amount_range,
                        })
                    return lst
            finally:
                db.close()
    except Exception as e:
        print(f"[DATA GENERATOR] Could not load vendors from DB, falling back to registry: {e}")
    return list(VENDOR_REGISTRY)


def _make_tx_time(base_date: datetime):
    """Return a datetime with realistic business-hour skew."""
    if random.random() < 0.88:
        hour = random.randint(8, 17)
        minute = random.randint(0, 59)
    else:
        hour = random.choice([7, 18, 19, 20, 21])
        minute = random.randint(0, 59)
    return base_date.replace(hour=hour, minute=minute, second=random.randint(0, 59))


def generate_synthetic_ledger(count: int = None, per_vendor: int = 100, vendor_override=None) -> str:
    """
    Generates corporate_ledger.csv with exactly `per_vendor` transactions for each vendor.
    Guarantees balanced ledger: every vendor gets `per_vendor` rows (default 100).
    
    - `per_vendor`: rows per vendor (default 100). If `count` is supplied as total, per_vendor is derived as count // num_vendors.
    - `vendor_override`: optional list of vendor dicts to generate for (used for single vendor provisioning)
    - Backward compat: if caller passes `count=5000` (old total), we interpret as per_vendor = count // vendors
    """
    ensure_directories()
    file_path = os.path.join(LEDGER_DIR, "corporate_ledger.csv")

    vendor_list = _resolve_vendor_list(vendor_override)

    # Backward compat: if count is an explicit total, derive per_vendor
    if count is not None:
        # caller explicitly wants total `count` rows balanced across vendors
        # e.g. count=5000 with 10 vendors => 500 per vendor
        # but for the canonical ledger we default to 100/vendor regardless of old default
        if len(vendor_list) > 0:
            derived = max(1, count // len(vendor_list))
            # only override if caller passed non-default total; default call count=None => keep per_vendor=100
            per_vendor = derived

    total_expected = len(vendor_list) * per_vendor
    start_date = datetime(2026, 1, 1)
    records = []
    txn_counter = 100000

    for vendor_info in vendor_list:
        v_id = vendor_info["vendor_id"]
        v_name = vendor_info["vendor_name"]
        dept = vendor_info["department"]
        cat = vendor_info["category"]
        min_amt, max_amt = vendor_info["amount_range"]

        # Generate baseline per_vendor rows for this vendor
        vendor_records = []
        for n in range(per_vendor):
            txn_counter += 1
            days_offset = random.randint(0, 180)
            txn_date = start_date + timedelta(days=days_offset)
            dt = _make_tx_time(txn_date)
            amount = round(random.uniform(min_amt, max_amt), 2)
            # vary description slightly
            desc_choices = [
                f"Standard quarterly procurement for {cat.lower()}",
                f"Invoice {v_name[:18]} — {cat}",
                f"Payment for {cat.lower()} services — {dept}",
                f"Approved vendor payout — {cat.lower()}",
            ]
            vendor_records.append({
                "transaction_id": f"TXN-{txn_counter}",
                "date": dt.strftime("%Y-%m-%d"),
                "time": dt.strftime("%H:%M:%S"),
                "vendor_id": v_id,
                "vendor_name": v_name,
                "amount": amount,
                "department": dept,
                "category": cat,
                "approval_status": "APPROVED",
                "payment_method": random.choice(["UPI", "NEFT", "RTGS", "CORPORATE_CARD"]),
                "description": random.choice(desc_choices),
                "is_injected_anomaly": False,
                "anomaly_type": "NONE"
            })

        # — Inject balanced anomalies *within* this vendor's slice (no cross-vendor mixing) —
        # ~7-9 anomalies per vendor (7-9%) ensures every vendor shows up in Anomaly Lab
        idx_pool = list(range(len(vendor_records)))
        random.shuffle(idx_pool)

        # Type 1: Threshold bypass (just below ₹1L) — 3 per vendor
        for k in range(min(3, len(idx_pool))):
            idx = idx_pool.pop()
            amt = round(random.uniform(90000.00, 99950.00), 2)
            vendor_records[idx]["amount"] = amt
            vendor_records[idx]["description"] = "Urgent project consulting fee (split order — near approval limit)"
            vendor_records[idx]["is_injected_anomaly"] = True
            vendor_records[idx]["anomaly_type"] = "THRESHOLD_BYPASS"

        # Type 2: Off-hours / weekend — 2 per vendor
        for k in range(min(2, len(idx_pool))):
            idx = idx_pool.pop()
            orig_dt = datetime.strptime(vendor_records[idx]["date"], "%Y-%m-%d")
            # move to a weekend (Saturday/Sunday) in same month window
            # find next Saturday
            days_to_sat = (5 - orig_dt.weekday()) % 7
            wknd = orig_dt + timedelta(days=days_to_sat)
            vendor_records[idx]["date"] = wknd.strftime("%Y-%m-%d")
            vendor_records[idx]["time"] = f"02:{random.randint(10,59):02d}:{random.randint(10,59):02d}"
            vendor_records[idx]["description"] = "After-hours emergency expense entry (weekend 02:xx)"
            vendor_records[idx]["is_injected_anomaly"] = True
            vendor_records[idx]["anomaly_type"] = "OFF_HOURS_ENTRY"

        # Type 3: Duplicate payment pair — 2 rows per vendor that share amount+date proximity
        # pick 2 pairs (4 indices) and make each pair share the same amount and close timestamps
        for _ in range(1):  # one duplicate pair per vendor (2 rows) — keeps total at exactly per_vendor
            if len(idx_pool) >= 2:
                i1 = idx_pool.pop()
                i2 = idx_pool.pop()
                # make them duplicates: same amount, dates within hours
                shared_amt = vendor_records[i1]["amount"]
                vendor_records[i2]["amount"] = shared_amt
                # align dates within 3 hours, keep same date but adjust time close
                dt1 = datetime.strptime(vendor_records[i1]["date"] + " " + vendor_records[i1]["time"], "%Y-%m-%d %H:%M:%S")
                dt2 = dt1 + timedelta(hours=random.randint(2, 6))
                vendor_records[i2]["date"] = dt2.strftime("%Y-%m-%d")
                vendor_records[i2]["time"] = dt2.strftime("%H:%M:%S")
                for ix in (i1, i2):
                    vendor_records[ix]["description"] = "Duplicate payment re-submission (48h window)"
                    vendor_records[ix]["is_injected_anomaly"] = True
                    vendor_records[ix]["anomaly_type"] = "DUPLICATE_PAYMENT"

        records.extend(vendor_records)

    # Shuffle globally then sort by date/time for realism
    random.shuffle(records)
    df = pd.DataFrame(records)
    df.sort_values(by=["date", "time"], inplace=True)
    # Re-sort to keep deterministic order but mixed vendors; then reset txn order display
    df.to_csv(file_path, index=False)
    print(f"[DATA GENERATOR] Created balanced ledger: {len(df)} records ({per_vendor}/vendor × {len(vendor_list)} vendors) at {file_path}")
    # also regenerate cleaned ledger so UI reflects immediately
    try:
        from backend.utils.data_cleaner import clean_raw_ledger
        clean_raw_ledger(input_path=file_path)
        print(f"[DATA GENERATOR] Cleaned ledger regenerated at {os.path.join(LEDGER_DIR, 'cleaned_ledger.csv')}")
    except Exception as e:
        print(f"[DATA GENERATOR] Cleaned ledger regeneration skipped: {e}")
    # retrain anomaly model if needed so new distribution is learned
    try:
        from backend.ml.train_anomaly_model import train as train_model
        # only retrain if there is a new ledger size materially different; we retrain async-light
        # For speed, skip heavy retrain on every injection unless called with new vendors
        pass
    except Exception:
        pass
    return file_path


def ensure_vendor_ledgers(vendor_id: str, vendor_name: str, department: str = None, category: str = None, per_vendor: int = 100):
    """
    Ensures the given vendor has exactly `per_vendor` ledger rows.
    If vendor already has >= per_vendor rows, does nothing.
    Otherwise appends fresh rows for that vendor (balanced anomalies included).
    Called automatically when a new vendor is provisioned.
    """
    ensure_directories()
    file_path = os.path.join(LEDGER_DIR, "corporate_ledger.csv")
    dept = department or "General"
    cat = category or "General"
    # Try resolve amount range
    base = VENDOR_MAP_BY_ID.get(vendor_id)
    amount_range = base["amount_range"] if base else (8000, 250000)

    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path, low_memory=False)
            existing = len(df[df["vendor_id"] == vendor_id]) if "vendor_id" in df.columns else 0
            if existing >= per_vendor:
                print(f"[DATA GENERATOR] Vendor {vendor_id} already has {existing} rows — no append needed.")
                return file_path
            need = per_vendor - existing
        except Exception as e:
            print(f"[DATA GENERATOR] Could not count existing ledgers for {vendor_id}: {e}")
            need = per_vendor
    else:
        need = per_vendor

    # Find max txn id to continue sequence
    try:
        df_existing = pd.read_csv(file_path, low_memory=False) if os.path.exists(file_path) else None
        if df_existing is not None and "transaction_id" in df_existing.columns and len(df_existing) > 0:
            max_num = 0
            for tid in df_existing["transaction_id"].astype(str):
                try:
                    num = int(tid.replace("TXN-", ""))
                    max_num = max(max_num, num)
                except: 
                    pass
            start_counter = max_num + 1
        else:
            start_counter = 300000
    except:
        start_counter = 300000

    new_records = []
    start_date = datetime(2026, 1, 1)
    for n in range(need):
        dt = _make_tx_time(start_date + timedelta(days=random.randint(0, 180)))
        amount = round(random.uniform(*amount_range), 2)
        new_records.append({
            "transaction_id": f"TXN-{start_counter + n}",
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M:%S"),
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "amount": amount,
            "department": dept,
            "category": cat,
            "approval_status": "APPROVED",
            "payment_method": random.choice(["UPI", "NEFT", "RTGS", "CORPORATE_CARD"]),
            "description": f"Standard procurement for {cat.lower()}",
            "is_injected_anomaly": False,
            "anomaly_type": "NONE"
        })

    # Inject a few anomalies within the new slice (proportional)
    if need >= 10:
        idxs = list(range(need))
        random.shuffle(idxs)
        # 3 threshold
        for k in range(min(3, len(idxs))):
            i = idxs.pop()
            new_records[i]["amount"] = round(random.uniform(90000, 99950), 2)
            new_records[i]["description"] = "Urgent project consulting fee (split order — near approval limit)"
            new_records[i]["is_injected_anomaly"] = True
            new_records[i]["anomaly_type"] = "THRESHOLD_BYPASS"
        # 2 off-hours
        for k in range(min(2, len(idxs))):
            i = idxs.pop()
            orig = datetime.strptime(new_records[i]["date"], "%Y-%m-%d")
            days_to_sat = (5 - orig.weekday()) % 7
            wknd = orig + timedelta(days=days_to_sat)
            new_records[i]["date"] = wknd.strftime("%Y-%m-%d")
            new_records[i]["time"] = f"02:{random.randint(10,59):02d}:{random.randint(10,59):02d}"
            new_records[i]["description"] = "After-hours emergency expense entry (weekend 02:xx)"
            new_records[i]["is_injected_anomaly"] = True
            new_records[i]["anomaly_type"] = "OFF_HOURS_ENTRY"
        # 1 duplicate pair
        if len(idxs) >= 2:
            i1 = idxs.pop(); i2 = idxs.pop()
            new_records[i2]["amount"] = new_records[i1]["amount"]
            dt1 = datetime.strptime(new_records[i1]["date"] + " " + new_records[i1]["time"], "%Y-%m-%d %H:%M:%S")
            dt2 = dt1 + timedelta(hours=random.randint(2, 6))
            new_records[i2]["date"] = dt2.strftime("%Y-%m-%d")
            new_records[i2]["time"] = dt2.strftime("%H:%M:%S")
            for ix in (i1, i2):
                new_records[ix]["description"] = "Duplicate payment re-submission (48h window)"
                new_records[ix]["is_injected_anomaly"] = True
                new_records[ix]["anomaly_type"] = "DUPLICATE_PAYMENT"

    # Append to CSV
    df_new = pd.DataFrame(new_records)
    if os.path.exists(file_path):
        df_old = pd.read_csv(file_path, low_memory=False)
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
        df_combined.sort_values(by=["date", "time"], inplace=True)
        df_combined.to_csv(file_path, index=False)
    else:
        df_new.sort_values(by=["date", "time"], inplace=True)
        df_new.to_csv(file_path, index=False)

    print(f"[DATA GENERATOR] Appended {need} balanced ledgers for vendor {vendor_id} ({vendor_name})")
    # regenerate cleaned ledger
    try:
        from backend.utils.data_cleaner import clean_raw_ledger
        clean_raw_ledger(input_path=file_path)
    except Exception as e:
        print(f"[DATA GENERATOR] Cleaned ledger regeneration after append skipped: {e}")
    return file_path

def generate_sample_invoices():
    """Generates sample vendor PDF invoices in INR (₹) for 3-way reconciliation testing."""
    ensure_directories()
    
    invoices = [
        {
            "filename": "INV-2026-001.pdf",
            "vendor_name": "TechCorp Systems India Pvt Ltd",
            "invoice_number": "INV-2026-001",
            "date": "2026-02-15",
            "subtotal": 142000.00,
            "tax": 25560.00, # 18% GST
            "total": 167560.00,
            "items": [("Enterprise Cloud License (1 Year)", 1, 142000.00)],
            "note": "Reconciles perfectly with ledger entry."
        },
        {
            "filename": "INV-2026-002.pdf",
            "vendor_name": "Global Travel Logistics Mumbai",
            "invoice_number": "INV-2026-002",
            "date": "2026-02-18",
            "subtotal": 48500.00,
            "tax": 2425.00,
            "total": 50925.00,
            "items": [("Executive Flights Mumbai to Delhi", 2, 48500.00)],
            "note": "Amount discrepancy vs general ledger."
        },
        {
            "filename": "INV-2026-003.pdf",
            "vendor_name": "Vertex Office Supplies Delhi",
            "invoice_number": "INV-2026-003",
            "date": "2026-02-20",
            "subtotal": 18500.00,
            "tax": 925.00,
            "total": 19425.00,
            "items": [("Ergonomic Chairs & Station Supplies", 5, 18500.00)],
            "note": "Standard operational purchase."
        },
        {
            "filename": "INV-2026-004.pdf",
            "vendor_name": "Apex Marketing Agency Bengaluru",
            "invoice_number": "INV-2026-004",
            "date": "2026-03-01",
            "subtotal": 450000.00,
            "tax": 81000.00,
            "total": 531000.00,
            "items": [("Q1 Brand Awareness Campaign", 1, 450000.00)],
            "note": "Unrecorded invoice not yet entered in CSV ledger."
        },
        {
            "filename": "INV-2026-005.pdf",
            "vendor_name": "Metro Cloud Hosting Hyderabad",
            "invoice_number": "INV-2026-005",
            "date": "2026-03-05",
            "subtotal": 210000.00,
            "tax": 37800.00,
            "total": 247800.00,
            "items": [("Dedicated Server Cluster Hosting", 1, 210000.00)],
            "note": "Duplicate invoice submission."
        }
    ]

    styles = getSampleStyleSheet()

    for inv in invoices:
        path = os.path.join(INVOICE_DIR, inv["filename"])
        doc = SimpleDocTemplate(path, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        story = []

        title_style = ParagraphStyle('InvTitle', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#2c2825'))
        body_style = ParagraphStyle('InvBody', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#44403c'))

        story.append(Paragraph(f"TAX INVOICE: {inv['invoice_number']}", title_style))
        story.append(Spacer(1, 10))
        
        meta_data = [
            [Paragraph(f"<b>Vendor:</b> {inv['vendor_name']}", body_style), Paragraph(f"<b>Date:</b> {inv['date']}", body_style)],
            [Paragraph(f"<b>GSTIN:</b> 27AAACT1024F1Z8 | <b>Inv #:</b> {inv['invoice_number']}", body_style), Paragraph(f"<b>Payment Terms:</b> Net 30", body_style)]
        ]
        meta_table = Table(meta_data, colWidths=[270, 270])
        meta_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
        story.append(meta_table)
        story.append(Spacer(1, 20))

        # Item Table in INR (₹)
        table_data = [["Description", "Qty", "Unit Price (Rs.)", "Total (Rs.)"]]
        for item in inv["items"]:
            table_data.append([item[0], str(item[1]), f"Rs. {item[2]:,.2f}", f"Rs. {item[1]*item[2]:,.2f}"])
        
        table_data.append(["", "", "Subtotal:", f"Rs. {inv['subtotal']:,.2f}"])
        table_data.append(["", "", "GST (18%):", f"Rs. {inv['tax']:,.2f}"])
        table_data.append(["", "", "GRAND TOTAL:", f"Rs. {inv['total']:,.2f}"])

        item_table = Table(table_data, colWidths=[260, 60, 110, 110])
        item_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#38322e')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#d8ceb3')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTNAME', (2,-1), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND', (2,-1), (-1,-1), colors.HexColor('#f5f0e6')),
        ]))
        story.append(item_table)
        story.append(Spacer(1, 20))
        story.append(Paragraph(f"<i>Note: {inv['note']}</i>", body_style))

        doc.build(story)
        print(f"[DATA GENERATOR] Generated invoice PDF: {path}")

def generate_policy_documents():
    """Generates realistic corporate policy PDFs tailored for Indian Operations (in INR ₹)."""
    ensure_directories()
    styles = getSampleStyleSheet()

    # 1. Travel & Expense Policy 2026 (India Operations)
    p1_path = os.path.join(POLICY_DIR, "Travel_and_Expense_Policy_2026.pdf")
    doc1 = SimpleDocTemplate(p1_path, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    s1 = []
    
    h1_style = ParagraphStyle('PolicyH1', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#2c2825'), spaceAfter=12)
    h2_style = ParagraphStyle('PolicyH2', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#38322e'), spaceBefore=10, spaceAfter=6)
    body_style = ParagraphStyle('PolicyBody', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#44403c'), leading=14, spaceAfter=8)

    s1.append(Paragraph("CORPORATE TRAVEL & EXPENSE POLICY (INDIA OPERATIONS - 2026)", h1_style))
    s1.append(Paragraph("<b>Effective Date:</b> January 1, 2026 | <b>Document ID:</b> POL-FIN-IND-2026-01", body_style))
    s1.append(Spacer(1, 10))

    s1.append(Paragraph("Section 1: Airfare and Lodging Approval Limits (INR)", h2_style))
    s1.append(Paragraph("1.1 Standard domestic flights must be booked in Economy Class at least 14 days in advance. Business Class airfare is strictly prohibited for domestic flights under 6 hours flight time.", body_style))
    s1.append(Paragraph("1.2 The maximum allowed lodging expense without Vice President sign-off is Rs. 7,500 (INR) per night for tier-1 cities (Mumbai, Delhi-NCR, Bengaluru, Hyderabad) and Rs. 4,500 per night for all tier-2/tier-3 cities.", body_style))
    s1.append(Paragraph("1.3 Any hotel expense exceeding Rs. 7,500 per night requires prior written authorization from the Department Vice President and Chief Financial Officer (CFO).", body_style))

    s1.append(Paragraph("Section 2: Daily Meal Allowances & GST Receipts", h2_style))
    s1.append(Paragraph("2.1 Employees are eligible for a maximum daily per diem meal allowance of Rs. 1,500 per day without individual receipts.", body_style))
    s1.append(Paragraph("2.2 For business meals with clients or vendors, expenses up to Rs. 4,000 per day are reimbursable provided itemized GST bills detailing food and beverages are submitted.", body_style))
    s1.append(Paragraph("2.3 Alcohol purchases are non-reimbursable unless explicitly approved in writing by a Senior Vice President for designated corporate client entertainment events.", body_style))

    s1.append(Paragraph("Section 3: Executive Approval Thresholds (INR)", h2_style))
    s1.append(Paragraph("3.1 Single transaction expenditures up to Rs. 50,000 require Department Director approval.", body_style))
    s1.append(Paragraph("3.2 Single transactions between Rs. 50,001 and Rs. 100,000 (Rs. 1 Lakh) require Vice President (VP) approval.", body_style))
    s1.append(Paragraph("3.3 Any transaction exceeding Rs. 100,000 (Rs. 1 Lakh) requires Chief Executive Officer (CEO) or CFO sign-off prior to NEFT/RTGS disbursement.", body_style))

    s1.append(PageBreak())

    s1.append(Paragraph("Section 4: Submission Deadlines & Split Payment Fraud", h2_style))
    s1.append(Paragraph("4.1 All expense reports must be submitted within 30 calendar days of the transaction date. Expenses submitted after 60 days will be permanently denied.", body_style))
    s1.append(Paragraph("4.2 Split Transaction Fraud: Artificial division of single invoices into smaller transactions (e.g., two Rs. 49,000 payments to avoid Rs. 50,000 Director threshold or two Rs. 98,000 payments to avoid Rs. 1,00,000 VP/CFO threshold) is a severe breach of corporate controls and subject to immediate disciplinary audit.", body_style))

    doc1.build(s1)
    print(f"[DATA GENERATOR] Generated Indian policy PDF: {p1_path}")

    # 2. Procurement Guidelines 2026 (India)
    p2_path = os.path.join(POLICY_DIR, "Procurement_and_Vendor_Guidelines_2026.pdf")
    doc2 = SimpleDocTemplate(p2_path, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    s2 = []

    s2.append(Paragraph("PROCUREMENT & VENDOR GUIDELINES (INDIA - 2026)", h1_style))
    s2.append(Paragraph("<b>Effective Date:</b> January 1, 2026 | <b>Document ID:</b> POL-PROC-IND-2026-02", body_style))
    s2.append(Spacer(1, 10))

    s2.append(Paragraph("Section 1: Vendor Selection & Competitive Bidding", h2_style))
    s2.append(Paragraph("1.1 Purchases exceeding Rs. 25,00,000 (Rs. 25 Lakhs) require a formal Request for Proposal (RFP) process with a minimum of three (3) independent competitive vendor bids.", body_style))
    s2.append(Paragraph("1.2 Sole-source vendor engagements over Rs. 1,00,000 (Rs. 1 Lakh) must include a Sole Source Justification Form approved by the Chief Procurement Officer.", body_style))

    s2.append(Paragraph("Section 2: 3-Way Reconciliation & GST Controls", h2_style))
    s2.append(Paragraph("2.1 Payments will only be released following complete 3-way matching between: (a) The Purchase Order (PO), (b) The Goods Receipt Note (GRN), and (c) The Vendor GST Invoice.", body_style))
    s2.append(Paragraph("2.2 Price variances exceeding 1.0% or Rs. 500.00 between invoice and PO must be flagged for manual Accounts Payable manager review.", body_style))

    doc2.build(s2)
    print(f"[DATA GENERATOR] Generated Indian procurement policy PDF: {p2_path}")

if __name__ == "__main__":
    generate_synthetic_ledger()
    generate_sample_invoices()
    generate_policy_documents()
