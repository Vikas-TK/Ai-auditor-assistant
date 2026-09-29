"""Machine-learning training & evaluation utilities for the anomaly engine.

Runtime scoring lives in ``backend/services/anomaly_engine.py``; this package holds the
offline pieces: the shared feature builder, the training script that persists the fitted
IsolationForest, and the injection-based evaluation harness.
"""
