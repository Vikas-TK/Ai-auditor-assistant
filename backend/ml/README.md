# Anomaly Model — training & evaluation

Module 2's risk engine is a **scikit-learn `IsolationForest`** (unsupervised) blended with
deterministic rule checks and SHAP explainability. This folder holds the offline pieces;
runtime scoring stays in [`backend/services/anomaly_engine.py`](../services/anomaly_engine.py).

| File | Role |
|---|---|
| `features.py` | `build_feature_frame()` — the one feature matrix definition, shared by training and serving |
| `train_anomaly_model.py` | fit the forest on the ledger, persist it |
| `artifact.py` | load/save the model bundle + `risk_from_raw()` (the 0-100 risk mapping) |
| `evaluate_anomaly_model.py` | injection-based evaluation on held-out rows |

## Dataset

Trains on `data/raw_ledgers/corporate_ledger.csv` — the **City of Chicago "Contracts"**
open dataset (`data.cityofchicago.org`, dataset `rsxa-df3t`): ~186k purchase-order rows,
13.7k vendors, real award amounts (incl. negative = contract de-obligations). No download
step — the file ships with the repo. `data_cleaner.load_and_preprocess_ledger()` maps the
raw columns, parses `Award Amount` (`"$-4,348.90"` → float), and derives the model features.

> The dataset has **no fraud labels** and **no transaction time** (`hour` is a constant, so
> it contributes nothing to this model). Evaluation therefore uses injected synthetic
> anomalies, not real labels.

## Train

```bash
python -m backend.ml.train_anomaly_model                       # defaults: 200 trees, contamination 0.03, seed 42
python -m backend.ml.train_anomaly_model --trees 300 --contamination 0.05 --seed 7
```

Writes `data/models/anomaly_iforest.joblib` (model + feature schema + category→code maps +
score range) and `anomaly_iforest.meta.json`. The API loads this artifact at startup; if it
is missing the first `/api/audit/anomalies` request trains one automatically. Re-run after
changing features or swapping the dataset.

### How the 0-100 risk score is built (`artifact.risk_from_raw` + `anomaly_engine`)

1. `IsolationForest.decision_function` → raw score; **< 0 means the model calls it an
   anomaly** (the fraction below 0 ≈ `contamination`).
2. Map raw → 0-100 pivoting at 0: raw `0` → risk **50**, most-normal → 0, most-anomalous →
   100. So **`risk >= 50` ⇔ the model flagged it**, and the flagged rate tracks
   `contamination` (default 3%).
3. Add deterministic rule weight: `THRESHOLD_BYPASS` +25, `DUPLICATE_PAYMENT` +25,
   `OFF_HOURS` +10. A *strong* violation (the first two) floors the row at 50 so it always
   reaches the report even if the ML score is unremarkable.
4. Bands: `>= 75` critical, `50–74` medium. The detail response is the top 500 by risk;
   `summary` carries the full counts.

Rule thresholds are configurable in `backend/config.py` / `.env`
(`ANOMALY_APPROVAL_THRESHOLDS`, `ANOMALY_THRESHOLD_BAND`, `ANOMALY_DUP_MIN_AMOUNT`,
`ANOMALY_DUP_WINDOW_DAYS`, `CURRENCY_SYMBOL`).

## Evaluate

```bash
python -m backend.ml.evaluate_anomaly_model                    # holdout 0.2, inject ~400
```

Holds out 20% of the ledger, plants four kinds of labelled anomalies (threshold-bypass,
duplicate payment, extreme outlier, rare vendor/department), scores with the trained model,
and reports ROC-AUC, PR-AUC + lift, precision@k, and per-kind recall for **ML-only** vs
**ML + rules**.

### What the current numbers say (Chicago data, defaults)

- **Extreme-amount outliers: ~100% recall (ML alone).** The forest keys on
  `is_negative_amount`, `log1p_amount_abs`, `dept_code`, `contract_type_code`.
- **Threshold-bypass (100%) and duplicate-payment (~75%) are caught by the rule engine**,
  not the ML — expected: those patterns look ordinary in an award-level dataset where
  round-number contracts and `$0.00` master agreements are common.
- `rare_vendor_dept`: weakly caught (~6%) — a soft signal with 13.7k vendors.
- ML-only ROC-AUC ≈ 0.60, PR-AUC ≈ 0.16 (~15× base rate). **ML + rules: ROC-AUC ≈ 0.83,
  PR-AUC ≈ 0.17, recall@risk50 ≈ 0.70.**
- With defaults the engine flags ~8–9% of rows (≈3% from the ML contamination cut, the rest
  from rule hits); `>= 75` critical is < 1%.

### Known limitations / follow-ups

- No transaction time in the source → `hour` is inert and `OFF_HOURS` degrades to
  "weekend approval date" (hence its lower +10 weight).
- The duplicate rule is a sort-adjacency heuristic; it misses dupes separated by a third
  same-key row and (by design) immaterial amounts below `ANOMALY_DUP_MIN_AMOUNT`.
- For a labelled/supervised follow-up, swap in one of the datasets below.

## Swapping datasets

Point `settings.RAW_LEDGER_PATH` (or drop a new `corporate_ledger.csv`) at another source,
make sure `data_cleaner`'s column mapping covers it, delete
`data/raw_ledgers/cleaned_ledger.csv`, then retrain. Labelled options for a proper
supervised follow-up: PaySim (`ealaxi/paysim1`), Kaggle credit-card fraud
(`mlg-ulb/creditcardfraud`), IEEE-CIS Fraud Detection.
