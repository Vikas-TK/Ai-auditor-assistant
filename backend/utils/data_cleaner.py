import os
import sys
from typing import Optional
import pandas as pd
import numpy as np
from datetime import datetime
from backend.config import settings


def coerce_amount(series: pd.Series) -> pd.Series:
    """Parse currency-formatted strings ('$-4,348.90', '($1,234.50)') into floats.

    Deliberately does NOT gate on ``dtype == object``: pandas >= 2.2 / 3.0 loads text
    columns as the 'str' dtype, so an ``== object`` check silently skips this cleanup and
    every value coerces to NaN -> 0.0 (which is exactly the bug this replaces).
    """
    cleaned = (
        series.astype(str)
        .str.strip()
        .str.replace(r"[\$,\s]", "", regex=True)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True)  # (1,234.00) -> -1234.00 accounting negatives
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def engineer_ledger_features(df: pd.DataFrame) -> pd.DataFrame:
    """Adds the derived columns the rule engine and ML model depend on.

    Idempotent-ish: recomputes time/amount/vendor features from ``amount`` + ``date``
    (+ optional ``time``) every call so a partially-populated frame is fully healed.
    """
    # Drop any stale derived columns so recomputation / merges don't collide (_x/_y suffixes).
    df = df.drop(columns=[
        c for c in ["amount_abs", "is_negative_amount", "day_of_week", "is_weekend",
                    "is_off_hours", "approval_month", "vendor_avg_amount",
                    "vendor_txn_count", "amount_ratio_to_avg"]
        if c in df.columns
    ])

    df["amount"] = coerce_amount(df["amount"]) if "amount" in df.columns else 0.0
    df["amount_abs"] = df["amount"].abs()
    df["is_negative_amount"] = (df["amount"] < 0).astype(int)

    df["date"] = pd.to_datetime(df["date"], errors="coerce") if "date" in df.columns else pd.Timestamp("2026-01-01")
    df["date"] = df["date"].fillna(pd.Timestamp("2026-01-01"))

    if "time" in df.columns:
        def _get_hour(t_str):
            try:
                return int(str(t_str).split(":")[0])
            except (ValueError, IndexError):
                return 12
        df["hour"] = df["time"].apply(_get_hour)
    else:
        df["hour"] = 12

    df["day_of_week"] = df["date"].dt.dayofweek
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["is_off_hours"] = ((df["hour"] < 6) | (df["hour"] >= 22) | (df["is_weekend"] == 1)).astype(int)
    df["approval_month"] = df["date"].dt.month

    vendor_stats = df.groupby("vendor_name")["amount_abs"].agg(["mean", "count"]).reset_index()
    vendor_stats.columns = ["vendor_name", "vendor_avg_amount", "vendor_txn_count"]
    df = df.merge(vendor_stats, on="vendor_name", how="left")
    df["vendor_avg_amount"] = df["vendor_avg_amount"].fillna(df["amount_abs"])
    df["vendor_txn_count"] = df["vendor_txn_count"].fillna(1).astype(int)
    df["amount_ratio_to_avg"] = df["amount_abs"] / (df["vendor_avg_amount"].abs() + 1e-5)

    return df


def clean_raw_ledger(input_path: str = None, output_path: str = None) -> pd.DataFrame:
    """Preprocesses raw export.csv / corporate_ledger.csv into cleaned_ledger.csv.
    Maps target columns:
    - 'Award Amount' -> 'amount'
    - 'Vendor Name' -> 'vendor_name'
    - 'Approval Date' -> 'date'
    - 'Department' -> 'department'
    """
    raw_path = input_path or settings.RAW_LEDGER_PATH
    out_path = output_path or settings.CLEANED_LEDGER_PATH

    if not os.path.exists(raw_path):
        export_path = os.path.join(settings.DATA_DIR, "raw_ledgers", "export.csv")
        if os.path.exists(export_path):
            raw_path = export_path
        else:
            from backend.utils.data_generator import generate_synthetic_ledger
            generate_synthetic_ledger()

    print(f"[DATA CLEANER] Loading raw dataset from: {raw_path}")
    df = pd.read_csv(raw_path, low_memory=False)
    print(f"[DATA CLEANER] Raw record count: {len(df):,} rows")

    # Target Column Mappings
    column_mapping = {
        'Award Amount': 'amount',
        'Vendor Name': 'vendor_name',
        'Approval Date': 'date',
        'Department': 'department',
        'Purchase Order (Contract) Number': 'transaction_id',
        'Vendor ID': 'vendor_id'
    }
    rename_dict = {k: v for k, v in column_mapping.items() if k in df.columns and v not in df.columns}
    if rename_dict:
        df = df.rename(columns=rename_dict)

    # Missing column handling & defaults
    if 'transaction_id' not in df.columns or df['transaction_id'].isna().all():
        df['transaction_id'] = [f"TXN-{100000 + i}" for i in range(len(df))]
    else:
        df['transaction_id'] = df['transaction_id'].fillna('').astype(str)

    if 'vendor_name' not in df.columns:
        df['vendor_name'] = 'UNASSIGNED_VENDOR'
    else:
        df['vendor_name'] = df['vendor_name'].astype(str).str.strip().fillna('UNASSIGNED_VENDOR')

    if 'department' not in df.columns:
        df['department'] = 'General Operations'

    # Ensure category column always exists for Ledger Data Center filtering
    if 'category' not in df.columns:
        # Derive category from department or set to General / Procurement Type
        if 'Procurement Type' in df.columns:
            df['category'] = df['Procurement Type'].fillna('General').astype(str)
        else:
            dept_to_cat = {
                'IT': 'Software & Hardware',
                'Travel': 'Flights & Hotels',
                'Operations': 'Office Supplies',
                'Marketing': 'Advertising & Media',
                'Finance': 'Advisory Services',
                'Logistics': 'Freight & Shipping',
                'HR': 'Events & Catering',
                'CHICAGO DEPARTMENT OF PUBLIC HEALTH': 'Healthcare Services',
                'DEPARTMENT OF PLANNING AND DEVELOPMENT': 'Infrastructure',
            }
            df['category'] = df['department'].map(dept_to_cat).fillna('General')
    else:
        df['category'] = df['category'].fillna('General').astype(str)

    if 'vendor_id' not in df.columns or df['vendor_id'].isna().all():
        from backend.utils.data_generator import VENDOR_NAME_TO_ID
        df['vendor_id'] = df['vendor_name'].map(VENDOR_NAME_TO_ID).fillna('UNASSIGNED')
    else:
        df['vendor_id'] = df['vendor_id'].astype(str).str.strip()

    # Amount + date + time + vendor-velocity feature extraction for ML & Rule checks
    df = engineer_ledger_features(df)

    # Persist dates as normalized YYYY-MM-DD strings
    df['date'] = pd.to_datetime(df['date'], errors='coerce').fillna(pd.Timestamp('2026-01-01')).dt.strftime('%Y-%m-%d')

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"[DATA CLEANER] Cleaned ledger saved to: {out_path} ({len(df):,} rows)")
    return df


def load_and_preprocess_ledger(file_path: str = None, vendor_id: Optional[str] = None) -> pd.DataFrame:
    """Loads CSV ledger (cleaned_ledger.csv or raw corporate_ledger.csv), handles missing values,
    extracts features, and optionally scopes the result to a single vendor_id."""
    target_path = file_path if file_path and os.path.exists(file_path) else settings.CLEANED_LEDGER_PATH

    if not os.path.exists(target_path):
        target_path = settings.RAW_LEDGER_PATH
        if not os.path.exists(target_path):
            from backend.utils.data_generator import generate_synthetic_ledger
            generate_synthetic_ledger()

    df = pd.read_csv(target_path, low_memory=False)

    required_cols = ['transaction_id', 'date', 'amount', 'vendor_name']
    if any(col not in df.columns for col in required_cols):
        df = clean_raw_ledger(input_path=target_path)
    elif (
        target_path == settings.CLEANED_LEDGER_PATH
        and os.path.exists(settings.RAW_LEDGER_PATH)
        and settings.RAW_LEDGER_PATH != settings.CLEANED_LEDGER_PATH
        and coerce_amount(df['amount']).abs().sum() == 0
        and len(df) > 5
    ):
        # A cleaned_ledger.csv with every amount == 0 is a corrupt artifact (historically
        # produced by the dtype-guarded parser). Rebuild it from the raw ledger.
        print("[DATA CLEANER] cleaned_ledger.csv has no non-zero amounts — rebuilding from raw.")
        df = clean_raw_ledger(input_path=settings.RAW_LEDGER_PATH)

    if 'vendor_id' not in df.columns:
        from backend.utils.data_generator import VENDOR_NAME_TO_ID
        df['vendor_id'] = df['vendor_name'].map(VENDOR_NAME_TO_ID).fillna('UNASSIGNED')

    # Ensure category sanitized for new rows too
    if 'category' not in df.columns:
        df['category'] = 'General'
    df['category'] = df['category'].fillna('General').astype(str)

    if vendor_id and vendor_id != 'ALL':
        df = df[df['vendor_id'] == vendor_id].reset_index(drop=True)

    df = engineer_ledger_features(df)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')

    return df


if __name__ == "__main__":
    print("==================================================================")
    print(" STEP 1: PREPROCESSING GENERAL LEDGER DATASET")
    print("==================================================================")
    df_cleaned = clean_raw_ledger()
    print(f"[SUCCESS] Dataset preprocessed successfully!")
    print(f"Total Rows: {len(df_cleaned):,}")
    print(f"Columns: {list(df_cleaned.columns)}")
