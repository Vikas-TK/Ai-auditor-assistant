"""Load/save helpers for the persisted anomaly-model bundle.

Kept separate from the training script so the serving path (`anomaly_engine.py`) can
import it without pulling in argparse / evaluation code.
"""
from __future__ import annotations

import os

import joblib
import numpy as np

from backend.config import settings

MODEL_DIR = os.path.join(settings.DATA_DIR, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "anomaly_iforest.joblib")
META_PATH = os.path.join(MODEL_DIR, "anomaly_iforest.meta.json")

# Bundle keys: model, feature_columns, category_maps, score_min, score_max, params
_REQUIRED_KEYS = {"model", "feature_columns", "category_maps", "score_min", "score_max"}


def save_bundle(bundle: dict) -> str:
    missing = _REQUIRED_KEYS - bundle.keys()
    if missing:
        raise ValueError(f"model bundle missing keys: {sorted(missing)}")
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(bundle, MODEL_PATH)
    return MODEL_PATH


def load_bundle() -> dict | None:
    """Return the persisted bundle, or ``None`` if no artifact has been trained yet."""
    if not os.path.exists(MODEL_PATH):
        return None
    bundle = joblib.load(MODEL_PATH)
    if not _REQUIRED_KEYS.issubset(bundle.keys()):
        return None
    return bundle


def risk_from_raw(raw_scores, bundle: dict):
    """Map IsolationForest ``decision_function`` output to a 0-100 risk score.

    The mapping pivots at 0 — the model's own contamination decision boundary — so
    ``risk >= 50`` corresponds exactly to "the model calls this an anomaly", and the
    flagged fraction tracks the ``contamination`` the model was trained with. Spans are
    the max of the training range and the current batch so out-of-distribution rows
    still land sensibly.
    """
    raw = np.asarray(raw_scores, dtype=float)
    batch_pos = float(raw.max()) if raw.size else 0.0
    batch_neg = float(raw.min()) if raw.size else 0.0
    pos = max(bundle.get("raw_pos_max", 0.0), batch_pos, 1e-9)
    neg = min(bundle.get("raw_neg_min", 0.0), batch_neg, -1e-9)
    return np.clip(
        np.where(raw < 0.0, 50.0 + 50.0 * (raw / neg), 50.0 * (1.0 - raw / pos)),
        0.0,
        100.0,
    )
