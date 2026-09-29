import os
import json
import numpy as np
import pandas as pd
from typing import List, Dict, Any
import shap

from backend.config import settings
from backend.utils.data_cleaner import load_and_preprocess_ledger
from backend.ml.artifact import load_bundle, risk_from_raw
from backend.ml.features import build_feature_frame

# Lazily-loaded, process-cached model bundle (see _get_model_bundle).
_MODEL_BUNDLE: Dict[str, Any] | None = None


def _get_model_bundle() -> Dict[str, Any]:
    """Return the persisted IsolationForest bundle, training one on first use if absent.

    The trained artifact lives at data/models/anomaly_iforest.joblib. Prefer running
    `python -m backend.ml.train_anomaly_model` explicitly (control over params); the
    in-process fallback here just keeps the endpoint working on a fresh checkout.
    """
    global _MODEL_BUNDLE
    if _MODEL_BUNDLE is not None:
        return _MODEL_BUNDLE

    bundle = load_bundle()
    if bundle is None:
        print("[ANOMALY] No persisted model found — training one now "
              "(run `python -m backend.ml.train_anomaly_model` to set params).")
        from backend.ml.train_anomaly_model import train as _train_model
        _train_model()
        bundle = load_bundle()

    if bundle is None:
        raise RuntimeError("Anomaly model bundle unavailable even after a training attempt.")

    _MODEL_BUNDLE = bundle
    return bundle


def reload_model_bundle() -> None:
    """Drop the cached bundle so the next request picks up a freshly trained artifact."""
    global _MODEL_BUNDLE
    _MODEL_BUNDLE = None

def _fmt_amount(amount: float) -> str:
    return f"{settings.CURRENCY_SYMBOL}{amount:,.2f}"


def _nearest_threshold(amount: float) -> float:
    """The approval limit an amount sits just under, or 0.0 if none applies."""
    band = settings.ANOMALY_THRESHOLD_BAND
    for t in sorted(settings.ANOMALY_APPROVAL_THRESHOLDS):
        if t * (1.0 - band) <= amount < t:
            return t
    return 0.0


def _canned_reason_code(amount: float, hour: int, rule_flags: list, shap_features: dict) -> str:
    reasons = []
    if "THRESHOLD_BYPASS" in rule_flags:
        t = _nearest_threshold(abs(amount))
        limit = f"the {_fmt_amount(t)} approval threshold" if t else "a round approval threshold"
        reasons.append(f"Amount {_fmt_amount(amount)} sits just below {limit}, a possible split-transaction pattern.")
    if "OFF_HOURS" in rule_flags:
        reasons.append("Entry dated to a weekend or outside normal business hours.")
    if "DUPLICATE_PAYMENT" in rule_flags:
        reasons.append("Identical vendor payment recorded within a short time window.")
    if shap_features.get("amount_ratio_to_avg", 0) > 2.0:
        reasons.append(f"Transaction amount is {shap_features['amount_ratio_to_avg']:.1f}x the historical vendor average.")
    return " | ".join(reasons) if reasons else "Statistical outlier based on combined transaction velocity, timing, and amount."


def _gemini_explain_one(args: dict) -> str:
    """Worker function: generates a single Gemini reason string. Returns canned text on any failure."""
    try:
        from backend.utils.helpers import get_gemini_client
        client = get_gemini_client()
        prompt = (
            "You are an AI financial auditor. In under 20 words explain why this general-ledger "
            "transaction is a financial-control risk based on these indicators:\n"
            f"Vendor: {args['vendor']} | Amount: {_fmt_amount(args['amount'])} | "
            f"Hour: {args['hour']:02d}:00 | Weekend: {args['is_weekend']} | "
            f"Rule flags: {', '.join(args['rule_flags']) or 'None'}"
        )
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[ANOMALY Gemini Worker] {e}")
        return _canned_reason_code(
            args['amount'], args['hour'], args['rule_flags'], args.get('shap_features', {})
        )


def generate_gemini_reason_code(txn_id: str, vendor: str, amount: float, hour: int, is_weekend: bool, rule_flags: list, shap_features: dict) -> tuple:
    """Single-call wrapper kept for backward-compat. Not used in the batch path."""
    if not settings.GEMINI_API_KEY:
        return _canned_reason_code(amount, hour, rule_flags, shap_features), False
    result = _gemini_explain_one({'vendor': vendor, 'amount': amount, 'hour': hour,
                                   'is_weekend': is_weekend, 'rule_flags': rule_flags,
                                   'shap_features': shap_features})
    return result, True

EMPTY_SUMMARY = {
    "total_transactions_audited": 0,
    "total_anomalies_flagged": 0,
    "critical_risk_count": 0,
    "medium_risk_count": 0,
    "total_at_risk_amount": 0.0
}


def run_anomaly_detection_pipeline(file_path: str = None, min_risk_score: float = 0.0, vendor_id: str = None, use_llm: bool = False) -> Dict[str, Any]:
    """
    Executes Rule-based + Isolation Forest ML + SHAP explainability anomaly detection on General Ledger.
    """
    df = load_and_preprocess_ledger(file_path, vendor_id=vendor_id)

    # A freshly provisioned vendor (or a vendor scope with no data yet) has zero rows —
    # IsolationForest can't fit on an empty/undersized frame, so short-circuit cleanly.
    if len(df) < 5:
        return {"summary": dict(EMPTY_SUMMARY, total_transactions_audited=len(df)), "anomalies": []}

    # 1. Deterministic Rule Engine (thresholds configurable — see backend/config.py)
    abs_amt = df['amount'].abs()
    band = settings.ANOMALY_THRESHOLD_BAND
    threshold_hit = pd.Series(False, index=df.index)
    for t in settings.ANOMALY_APPROVAL_THRESHOLDS:
        threshold_hit |= (abs_amt >= t * (1.0 - band)) & (abs_amt < t)
    threshold_set = set(df[threshold_hit].index)
    offhours_set = set(df[df['is_off_hours'] == 1].index)

    df_sorted = df.sort_values(by=['vendor_name', 'amount', 'date']).copy()
    same_vendor = df_sorted['vendor_name'] == df_sorted['vendor_name'].shift(-1)
    same_amount = (df_sorted['amount'] - df_sorted['amount'].shift(-1)).abs() < 0.01
    material = df_sorted['amount'].abs() >= settings.ANOMALY_DUP_MIN_AMOUNT
    dt_col = pd.to_datetime(df_sorted['date'])
    days_diff = (dt_col.shift(-1) - dt_col).dt.days.abs() <= settings.ANOMALY_DUP_WINDOW_DAYS
    dup_mask = same_vendor & same_amount & days_diff & material
    dup_set = set(df_sorted[dup_mask].index).union(set(df_sorted[dup_mask.shift(1).fillna(False)].index))

    rule_flags_list = []
    for idx in range(len(df)):
        f = []
        if idx in threshold_set:
            f.append("THRESHOLD_BYPASS")
        if idx in offhours_set:
            f.append("OFF_HOURS")
        if idx in dup_set:
            f.append("DUPLICATE_PAYMENT")
        rule_flags_list.append(f)

    df['rule_flags'] = rule_flags_list

    # Per-flag risk contribution. THRESHOLD_BYPASS / DUPLICATE_PAYMENT are hard control
    # violations; OFF_HOURS here is only "approval dated to a weekend" (no txn time in the
    # data) so it is a soft nudge, not a flag that forces the row onto the report.
    RULE_WEIGHTS = {"THRESHOLD_BYPASS": 25.0, "DUPLICATE_PAYMENT": 25.0, "OFF_HOURS": 10.0}
    STRONG_FLAGS = {"THRESHOLD_BYPASS", "DUPLICATE_PAYMENT"}

    # 2. Isolation Forest ML Anomaly Scoring (pre-trained, persisted model)
    bundle = _get_model_bundle()
    iso_model = bundle["model"]
    feature_cols = bundle["feature_columns"]
    X, _ = build_feature_frame(df, category_maps=bundle["category_maps"])

    # Isolation Forest outputs raw decision scores (< 0 = model calls it an anomaly).
    raw_scores = iso_model.decision_function(X)

    # Map to 0-100 risk, pivoting at the model's contamination boundary so risk >= 50
    # means "the model flags this" (see artifact.risk_from_raw).
    normalized_scores = risk_from_raw(raw_scores, bundle)
    
    # Add each fired rule's weight; a strong deterministic violation always surfaces at
    # >= medium risk (50) even when the ML score alone is unremarkable.
    rule_bonus = df['rule_flags'].apply(lambda fs: sum(RULE_WEIGHTS.get(f, 0.0) for f in fs))
    has_strong = df['rule_flags'].apply(lambda fs: any(f in STRONG_FLAGS for f in fs))
    risk = np.clip(normalized_scores + rule_bonus.to_numpy(), 0.0, 100.0)
    risk = np.where(has_strong.to_numpy(), np.clip(risk, 50.0, 100.0), risk)
    df['risk_score'] = np.round(risk, 1)

    # Filter high risk items
    high_risk_df = df[df['risk_score'] >= min_risk_score].sort_values(by='risk_score', ascending=False)
    flagged_indices = df[df['risk_score'] >= 50.0].index

    # Vectorized Summary Statistics
    critical_risk_count = int((df['risk_score'] >= 75.0).sum())
    medium_risk_count = int(((df['risk_score'] >= 50.0) & (df['risk_score'] < 75.0)).sum())
    total_anomalies_flagged = critical_risk_count + medium_risk_count
    total_at_risk_amount = float(df[df['risk_score'] >= 50.0]['amount'].sum())

    summary = {
        "total_transactions_audited": len(df),
        "total_anomalies_flagged": total_anomalies_flagged,
        "critical_risk_count": critical_risk_count,
        "medium_risk_count": medium_risk_count,
        "total_at_risk_amount": total_at_risk_amount
    }

    # Filter items to return in detailed anomaly response. Always cap the detail list:
    # per-row SHAP + Gemini reason codes are O(rows), and nobody hand-reviews >500 line
    # items — the full counts still live in `summary`.
    DETAIL_CAP = 500
    output_df = df[df['risk_score'] >= min_risk_score].sort_values(by='risk_score', ascending=False)
    if len(output_df) > DETAIL_CAP:
        output_df = output_df.head(DETAIL_CAP)

    # 3. Compute SHAP Values for detailed output items
    explainer = shap.TreeExplainer(iso_model)
    if not output_df.empty:
        X_out = X.loc[output_df.index]
        shap_values = explainer.shap_values(X_out)
        shap_map = {idx: row_shap for idx, row_shap in zip(output_df.index, shap_values)}
    else:
        shap_map = {}

    # 4. Build the base anomaly records (fast — no LLM yet)
    base_records = []
    for orig_idx, row in output_df.iterrows():
        row_shap = shap_map.get(orig_idx, np.zeros(len(feature_cols)))
        shap_dict = {col: float(np.round(val, 3)) for col, val in zip(feature_cols, row_shap)}
        rule_list = row['rule_flags']
        base_records.append({
            "transaction_id": str(row['transaction_id']),
            "date": str(row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else row['date']),
            "time": f"{int(row['hour']):02d}:00:00",
            "vendor_name": str(row['vendor_name']),
            "department": str(row.get('department', 'General')),
            "amount": float(row['amount']),
            "risk_score": float(row['risk_score']),
            "rule_flags": rule_list,
            "primary_reason": _canned_reason_code(float(row['amount']), int(row['hour']), rule_list, shap_dict),
            "shap_breakdown": shap_dict,
            "_llm_args": {   # only used if use_llm=True
                "vendor": str(row['vendor_name']),
                "amount": float(row['amount']),
                "hour": int(row['hour']),
                "is_weekend": bool(row['is_weekend']),
                "rule_flags": rule_list,
                "shap_features": shap_dict,
            }
        })

    # 5. Optional: enrich top-N records with Gemini explanations concurrently
    #    use_llm=True fires all calls in parallel with a 12s wall-clock budget.
    if use_llm and settings.GEMINI_API_KEY:
        import concurrent.futures
        LLM_TOP_N = 5          # enrich only the 5 highest-risk items
        LLM_TIMEOUT = 12       # total wall-clock seconds for the whole batch
        to_enrich = [r for r in base_records if r['risk_score'] >= 50.0][:LLM_TOP_N]
        arg_list = [r['_llm_args'] for r in to_enrich]
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=LLM_TOP_N) as pool:
                results = list(pool.map(_gemini_explain_one, arg_list, timeout=LLM_TIMEOUT))
            for record, explanation in zip(to_enrich, results):
                record['primary_reason'] = explanation
        except Exception as e:
            print(f"[ANOMALY LLM batch] timed-out or failed — using canned reasons. {e}")

    anomalies = []
    for record in base_records:
        record.pop('_llm_args', None)   # strip internal key before serializing
        anomalies.append(record)

    return {
        "summary": summary,
        "anomalies": anomalies
    }


if __name__ == "__main__":
    import time
    print("==================================================================")
    print(" RUNNING ISOLATION FOREST ANOMALY DETECTION PIPELINE")
    print(" (to (re)train the model: python -m backend.ml.train_anomaly_model)")
    print("==================================================================")
    start_time = time.time()
    result = run_anomaly_detection_pipeline()
    elapsed = time.time() - start_time

    summary = result["summary"]
    print(f"[SUCCESS] Pipeline completed in {elapsed:.2f} seconds.")
    print(f"Total Transactions Audited: {summary['total_transactions_audited']:,}")
    print(f"Total Anomalies Flagged:    {summary['total_anomalies_flagged']:,}")
    print(f"Critical Risk Items (>=75%):{summary['critical_risk_count']:,}")
    print(f"Medium Risk Items (50-74%): {summary['medium_risk_count']:,}")
    print(f"Total At-Risk Exposure:     INR {summary['total_at_risk_amount']:,.2f}")
