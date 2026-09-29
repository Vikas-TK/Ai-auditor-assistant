"""Shared feature-matrix builder for the anomaly IsolationForest.

Single source of truth imported by BOTH training (`backend/ml/train_anomaly_model.py`)
and serving (`backend/services/anomaly_engine.py`) so the column set and categorical
encoding never drift between the two.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Order is significant: SHAP breakdowns and the frontend explainer reference features
# positionally / by name. The first six names are kept for backwards compatibility with
# the original engine and the SHAP drawer in the SPA (shap.amount, shap.hour, ...).
FEATURE_COLUMNS = [
    "amount",
    "hour",
    "is_weekend",
    "vendor_id_code",
    "dept_code",
    "amount_ratio_to_avg",
    "log1p_amount_abs",
    "is_negative_amount",
    "vendor_txn_count",
    "contract_type_code",
    "approval_month",
]

# code column -> source column in the cleaned ledger frame
CATEGORICAL_SOURCES = {
    "vendor_id_code": "vendor_id",
    "dept_code": "department",
    "contract_type_code": "Contract Type",
}

_NUMERIC_DEFAULTS = {
    "amount": 0.0,
    "hour": 12,
    "is_weekend": 0,
    "amount_ratio_to_avg": 0.0,
    "is_negative_amount": 0,
    "vendor_txn_count": 1,
    "approval_month": 1,
}


def build_feature_frame(df: pd.DataFrame, category_maps: dict | None = None):
    """Build the numeric feature matrix for the IsolationForest.

    Parameters
    ----------
    df:
        A ledger frame that has already been through
        ``data_cleaner.engineer_ledger_features`` (so ``amount_abs`` etc. exist).
    category_maps:
        ``None`` during training -> maps are learned from ``df`` and returned.
        A dict during serving -> the frozen maps are applied; values unseen at
        training time encode to ``-1``.

    Returns
    -------
    (X, category_maps): ``(pd.DataFrame, dict)``
    """
    df = df.copy()

    for col, default in _NUMERIC_DEFAULTS.items():
        if col not in df.columns:
            df[col] = default

    if "amount_abs" not in df.columns:
        df["amount_abs"] = df["amount"].abs()
    df["log1p_amount_abs"] = np.log1p(df["amount_abs"].clip(lower=0.0))

    learn = category_maps is None
    category_maps = {} if learn else dict(category_maps)

    for code_col, src_col in CATEGORICAL_SOURCES.items():
        if src_col in df.columns:
            values = df[src_col].where(df[src_col].notna(), "__MISSING__").astype(str)
        else:
            values = pd.Series(["__MISSING__"] * len(df), index=df.index)

        if learn:
            category_maps[code_col] = {v: i for i, v in enumerate(sorted(values.unique(), key=str))}

        df[code_col] = values.map(category_maps[code_col]).fillna(-1).astype(int)

    X = df.reindex(columns=FEATURE_COLUMNS).apply(pd.to_numeric, errors="coerce").fillna(0.0).astype(float)
    return X, category_maps
