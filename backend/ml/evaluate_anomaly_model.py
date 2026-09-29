"""Evaluate the persisted IsolationForest by injecting known anomalies into held-out data.

The Chicago Contracts ledger has no fraud labels, so we measure detection quality the way
it is normally done for unlabelled anomaly detection: hold out a slice of real rows, plant
a controlled set of synthetic anomalies with known labels, score everything with the
trained model, and report ranking metrics.

    python -m backend.ml.evaluate_anomaly_model
    python -m backend.ml.evaluate_anomaly_model --holdout 0.2 --seed 1 --inject 400
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from backend.config import settings
from backend.ml.artifact import load_bundle, risk_from_raw
from backend.ml.features import build_feature_frame
from backend.utils.data_cleaner import engineer_ledger_features, load_and_preprocess_ledger

INJECTORS = ("threshold_bypass", "duplicate_payment", "extreme_outlier", "rare_vendor_dept")


def _ml_risk_scores(df: pd.DataFrame, bundle: dict) -> np.ndarray:
    """Normalized 0-100 ML risk score — mirrors anomaly_engine's ML step (no rule bonus)."""
    X, _ = build_feature_frame(df, category_maps=bundle["category_maps"])
    raw = bundle["model"].decision_function(X)
    return risk_from_raw(raw, bundle)


def _rule_signals(df: pd.DataFrame):
    """Replicates anomaly_engine's rule bonus. Returns (bonus, has_strong_flag)."""
    df = df.reset_index(drop=True)
    abs_amt = df["amount"].abs()
    band = settings.ANOMALY_THRESHOLD_BAND
    thr = pd.Series(False, index=df.index)
    for t in settings.ANOMALY_APPROVAL_THRESHOLDS:
        thr |= (abs_amt >= t * (1.0 - band)) & (abs_amt < t)
    offhours = (df.get("is_off_hours", pd.Series(0, index=df.index)) == 1).to_numpy()

    s = df.sort_values(["vendor_name", "amount", "date"])
    same_vendor = s["vendor_name"] == s["vendor_name"].shift(-1)
    same_amount = (s["amount"] - s["amount"].shift(-1)).abs() < 0.01
    material = s["amount"].abs() >= settings.ANOMALY_DUP_MIN_AMOUNT
    days = (pd.to_datetime(s["date"]).shift(-1) - pd.to_datetime(s["date"])).dt.days.abs() <= settings.ANOMALY_DUP_WINDOW_DAYS
    dup = same_vendor & same_amount & days & material
    dup_idx = set(s[dup].index).union(set(s[dup.shift(1).fillna(False)].index))
    dup_hit = df.index.isin(dup_idx)

    thr_hit = thr.to_numpy()
    bonus = thr_hit * 25.0 + offhours * 10.0 + dup_hit * 25.0
    has_strong = thr_hit | dup_hit
    return bonus, has_strong


def inject_anomalies(df: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Return a copy of df with ~n planted anomalies and an ``is_anomaly`` label column."""
    df = df.reset_index(drop=True).copy()
    df["is_anomaly"] = 0
    df["anomaly_kind"] = ""
    p999 = df["amount_abs"].quantile(0.999) or df["amount_abs"].max() or 1.0
    per_kind = max(1, n // len(INJECTORS))

    new_rows = []
    for kind in INJECTORS:
        victims = rng.choice(df.index.values, size=min(per_kind, len(df)), replace=False)
        for idx in victims:
            if kind == "threshold_bypass":
                t = float(rng.choice(settings.ANOMALY_APPROVAL_THRESHOLDS))
                df.at[idx, "amount"] = t * float(rng.uniform(1.0 - settings.ANOMALY_THRESHOLD_BAND + 1e-4, 0.9999))
                df.at[idx, "is_anomaly"] = 1
                df.at[idx, "anomaly_kind"] = kind
            elif kind == "extreme_outlier":
                df.at[idx, "amount"] = float(p999 * rng.uniform(6, 40))
                df.at[idx, "is_anomaly"] = 1
                df.at[idx, "anomaly_kind"] = kind
            elif kind == "rare_vendor_dept":
                depts = df["department"].dropna().unique()
                cur = df.at[idx, "department"]
                choices = [d for d in depts if d != cur]
                if choices:
                    df.at[idx, "department"] = rng.choice(choices)
                    df.at[idx, "is_anomaly"] = 1
                    df.at[idx, "anomaly_kind"] = kind
            elif kind == "duplicate_payment":
                dup = df.loc[idx].to_dict()
                dup["transaction_id"] = f"{dup['transaction_id']}-DUP"
                dup["is_anomaly"] = 1
                dup["anomaly_kind"] = kind
                new_rows.append(dup)

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    # Recompute derived features so the planted amounts/departments actually propagate.
    df = engineer_ledger_features(df)
    return df


def _precision_at_k(labels: np.ndarray, scores: np.ndarray, k: int) -> float:
    order = np.argsort(scores)[::-1][:k]
    return float(labels[order].sum() / max(1, len(order)))


def evaluate(holdout: float = 0.2, seed: int = 42, inject: int = 400) -> dict:
    bundle = load_bundle()
    if bundle is None:
        raise RuntimeError("No trained model. Run: python -m backend.ml.train_anomaly_model")

    rng = np.random.default_rng(seed)
    df = load_and_preprocess_ledger()
    holdout_df = df.sample(frac=holdout, random_state=seed)
    print(f"[EVAL] holdout rows={len(holdout_df):,}  injecting ~{inject} anomalies")

    planted = inject_anomalies(holdout_df, inject, rng)
    labels = planted["is_anomaly"].to_numpy()
    scores = _ml_risk_scores(planted, bundle)
    bonus, has_strong = _rule_signals(planted)
    combined = np.clip(scores + bonus, 0.0, 100.0)
    combined = np.where(has_strong, np.clip(combined, 50.0, 100.0), combined)  # strong violations always >= medium
    base_rate = labels.mean()

    metrics = {
        "rows": int(len(planted)),
        "injected": int(labels.sum()),
        "base_rate": round(float(base_rate), 5),
        "roc_auc": round(float(roc_auc_score(labels, scores)), 4),
        "pr_auc": round(float(average_precision_score(labels, scores)), 4),
        "pr_auc_lift": round(float(average_precision_score(labels, scores) / base_rate), 2),
        "precision_at_50": round(_precision_at_k(labels, scores, 50), 3),
        "precision_at_100": round(_precision_at_k(labels, scores, 100), 3),
        "precision_at_500": round(_precision_at_k(labels, scores, 500), 3),
        "recall_at_risk_50": round(float(labels[scores >= 50].sum() / max(1, labels.sum())), 3),
        "recall_at_risk_75": round(float(labels[scores >= 75].sum() / max(1, labels.sum())), 3),
        "combined_roc_auc": round(float(roc_auc_score(labels, combined)), 4),
        "combined_pr_auc": round(float(average_precision_score(labels, combined)), 4),
        "combined_recall_at_risk_50": round(float(labels[combined >= 50].sum() / max(1, labels.sum())), 3),
    }

    print("\n== detection metrics (injected anomalies as ground truth) ==")
    for k, v in metrics.items():
        print(f"  {k:28s} {v}")

    print("\n== recall by injected anomaly kind (risk >= 50) ==")
    for kind in INJECTORS:
        mask = planted["anomaly_kind"] == kind
        if mask.any():
            m = mask.to_numpy()
            print(f"  {kind:20s} ML={ (scores[m] >= 50).mean():.0%}   "
                  f"ML+rules={ (combined[m] >= 50).mean():.0%}   (n={int(mask.sum())})")

    print("\n== global feature importance (mean |SHAP| on a 2k sample) ==")
    import shap
    sample = build_feature_frame(planted, bundle["category_maps"])[0].sample(
        min(2000, len(planted)), random_state=seed
    )
    sv = shap.TreeExplainer(bundle["model"]).shap_values(sample)
    imp = np.abs(sv).mean(axis=0)
    for name, val in sorted(zip(bundle["feature_columns"], imp), key=lambda t: -t[1]):
        print(f"  {name:20s} {val:.4f}")

    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Injection-based evaluation of the anomaly model.")
    ap.add_argument("--holdout", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--inject", type=int, default=400)
    a = ap.parse_args()
    evaluate(holdout=a.holdout, seed=a.seed, inject=a.inject)
