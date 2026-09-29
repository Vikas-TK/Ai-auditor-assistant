"""Fit the IsolationForest anomaly model on the general ledger and persist it.

Usage:
    python -m backend.ml.train_anomaly_model
    python -m backend.ml.train_anomaly_model --trees 300 --contamination 0.05 --seed 7

Writes:
    data/models/anomaly_iforest.joblib   (model + feature schema + category maps + score norm)
    data/models/anomaly_iforest.meta.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import IsolationForest

from backend.config import settings
from backend.ml.artifact import META_PATH, MODEL_PATH, risk_from_raw, save_bundle
from backend.ml.features import FEATURE_COLUMNS, build_feature_frame
from backend.utils.data_cleaner import load_and_preprocess_ledger

DEFAULT_TREES = 200
DEFAULT_CONTAMINATION = 0.03
DEFAULT_SEED = 42


def train(
    n_estimators: int = DEFAULT_TREES,
    contamination: float = DEFAULT_CONTAMINATION,
    random_state: int = DEFAULT_SEED,
    ledger_path: str | None = None,
) -> str:
    df = load_and_preprocess_ledger(file_path=ledger_path)
    nonzero = int((df["amount"] != 0).sum())
    if nonzero == 0:
        raise RuntimeError(
            "Every ledger amount is 0 — the source data or the cleaner is broken. "
            "Refusing to train a meaningless model."
        )

    X, category_maps = build_feature_frame(df)
    print(f"[TRAIN] rows={len(df):,}  non-zero amounts={nonzero:,}  features={len(FEATURE_COLUMNS)}")

    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        n_jobs=-1,
        random_state=random_state,
    )
    model.fit(X)

    raw = model.decision_function(X)
    score_min, score_max = float(raw.min()), float(raw.max())

    bundle = {
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "category_maps": category_maps,
        "score_min": score_min,
        "score_max": score_max,
        "raw_pos_max": float(max(raw.max(), 1e-9)),
        "raw_neg_min": float(min(raw.min(), -1e-9)),
        "params": {
            "n_estimators": n_estimators,
            "contamination": contamination,
            "random_state": random_state,
        },
    }
    save_bundle(bundle)

    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "train_rows": int(len(df)),
        "nonzero_amount_rows": nonzero,
        "negative_amount_rows": int(df.get("is_negative_amount", np.zeros(len(df))).sum()),
        "feature_columns": FEATURE_COLUMNS,
        "score_min": score_min,
        "score_max": score_max,
        "ledger_path": ledger_path or settings.CLEANED_LEDGER_PATH,
        "n_estimators": n_estimators,
        "contamination": contamination,
        "random_state": random_state,
    }
    with open(META_PATH, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    norm = risk_from_raw(raw, bundle)
    print(f"[TRAIN] saved model -> {MODEL_PATH}")
    print(f"[TRAIN] saved meta  -> {META_PATH}")
    print(
        f"[TRAIN] risk score: p50={np.percentile(norm, 50):.1f} "
        f"p90={np.percentile(norm, 90):.1f} p95={np.percentile(norm, 95):.1f} "
        f"p99={np.percentile(norm, 99):.1f} max={norm.max():.1f}"
    )
    print(
        f"[TRAIN] risk>=50 (ML only): {int((norm >= 50).sum()):,} "
        f"({(norm >= 50).mean():.1%})  |  risk>=75: {int((norm >= 75).sum()):,}"
    )
    return MODEL_PATH


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train the IsolationForest ledger anomaly model.")
    p.add_argument("--trees", type=int, default=DEFAULT_TREES, help="n_estimators (default 200)")
    p.add_argument("--contamination", type=float, default=DEFAULT_CONTAMINATION, help="expected anomaly fraction (default 0.03)")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random_state (default 42)")
    p.add_argument("--ledger", type=str, default=None, help="optional explicit ledger CSV path")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    train(
        n_estimators=args.trees,
        contamination=args.contamination,
        random_state=args.seed,
        ledger_path=args.ledger,
    )
