"""Seen It evaluation harness package (P2).

What this module does:
    Marks `eval` as a Python package exposing P2's evaluation metrics
    (`eval.metrics`), chart generators (`eval.charts`), and CLI evaluation
    runner (`eval.run_eval`).

Use cases:
    - Running build-set threshold calibration (`python3 -m eval.run_eval --split build --sweep`).
    - Running held-out evaluation and `relook` ablation (`python3 -m eval.run_eval --split heldout --compare-relook`).

What this module must NOT do:
    - Must never import P1's `eval/baseline.py` or `eval/stress.py` at package import time.
    - Must never commit large videos or raw merchant images into `eval/results/`.
"""
