"""
UrbanSense AI — Evaluation & Review of Trained YOLO Models
===========================================================
Audits training runs in backend/app/models/urbansense_runs.
Compares candidate_a_baseline and candidate_b_oversampled.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path


def evaluate_run(run_dir: Path) -> dict:
    csv_file = run_dir / "results.csv"
    if not csv_file.exists():
        return {"error": "results.csv not found"}

    with open(csv_file, "r", encoding="utf-8") as f:
        rows = [{k.strip(): float(v.strip()) for k, v in r.items() if v.strip()} for r in csv.DictReader(f)]

    epochs = len(rows)
    best_50_idx = max(range(epochs), key=lambda i: rows[i].get("metrics/mAP50(B)", 0))
    best_95_idx = max(range(epochs), key=lambda i: rows[i].get("metrics/mAP50-95(B)", 0))

    initial = rows[0]
    peak_50 = rows[best_50_idx]
    peak_95 = rows[best_95_idx]
    final = rows[-1]

    weights = {}
    weights_dir = run_dir / "weights"
    if weights_dir.exists():
        for w in weights_dir.iterdir():
            weights[w.name] = w.stat().st_size

    return {
        "run_name": run_dir.name,
        "total_epochs": epochs,
        "weights": weights,
        "initial": {
            "epoch": int(initial["epoch"]),
            "train_box_loss": initial.get("train/box_loss"),
            "val_box_loss": initial.get("val/box_loss"),
            "precision": initial.get("metrics/precision(B)"),
            "recall": initial.get("metrics/recall(B)"),
            "mAP50": initial.get("metrics/mAP50(B)"),
            "mAP50_95": initial.get("metrics/mAP50-95(B)"),
        },
        "peak_mAP50": {
            "epoch": int(peak_50["epoch"]),
            "train_box_loss": peak_50.get("train/box_loss"),
            "val_box_loss": peak_50.get("val/box_loss"),
            "train_cls_loss": peak_50.get("train/cls_loss"),
            "val_cls_loss": peak_50.get("val/cls_loss"),
            "precision": peak_50.get("metrics/precision(B)"),
            "recall": peak_50.get("metrics/recall(B)"),
            "mAP50": peak_50.get("metrics/mAP50(B)"),
            "mAP50_95": peak_50.get("metrics/mAP50-95(B)"),
        },
        "peak_mAP50_95": {
            "epoch": int(peak_95["epoch"]),
            "mAP50": peak_95.get("metrics/mAP50(B)"),
            "mAP50_95": peak_95.get("metrics/mAP50-95(B)"),
        },
        "final": {
            "epoch": int(final["epoch"]),
            "train_box_loss": final.get("train/box_loss"),
            "val_box_loss": final.get("val/box_loss"),
            "train_cls_loss": final.get("train/cls_loss"),
            "val_cls_loss": final.get("val/cls_loss"),
            "precision": final.get("metrics/precision(B)"),
            "recall": final.get("metrics/recall(B)"),
            "mAP50": final.get("metrics/mAP50(B)"),
            "mAP50_95": final.get("metrics/mAP50-95(B)"),
        },
    }


def main():
    base = Path("backend/app/models/urbansense_runs")
    reports = {}
    for sub in sorted(base.iterdir()):
        if sub.is_dir():
            rep = evaluate_run(sub)
            reports[sub.name] = rep

    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
