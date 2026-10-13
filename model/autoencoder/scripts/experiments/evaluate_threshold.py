import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

AUTOENCODER_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = AUTOENCODER_DIR.parents[1]

DATA_DIR = (
    PROJECT_ROOT
    / "data-pipeline"
    / "output"
    / "NSL-KDD"
    / "feature_engineered"
)
MODEL_DIR = AUTOENCODER_DIR
RESULTS_DIR = MODEL_DIR / "results"
CSV_DIR = RESULTS_DIR / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

if str(MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(MODEL_DIR))

from autoencoder_model import Autoencoder


def main():
    # 1. โหลดข้อมูล
    train_features = pd.read_csv(
        DATA_DIR / "KDDTrain_features.csv"
    )
    train_targets = pd.read_csv(
        DATA_DIR / "KDDTrain_targets.csv"
    )
    test_features = pd.read_csv(
        DATA_DIR / "KDDTest_features.csv"
    )
    test_targets = pd.read_csv(
        DATA_DIR / "KDDTest_targets.csv"
    )

    # 2. โหลด Scaler และรายการ Features
    scaler = joblib.load(MODEL_DIR / "scaler.pkl")
    feature_columns = (
        MODEL_DIR / "feature_columns.txt"
    ).read_text(encoding="utf-8").splitlines()

    # 3. โหลดโมเดล
    model = Autoencoder(input_dim=len(feature_columns))
    model.load_state_dict(
        torch.load(
            MODEL_DIR / "autoencoder.pth",
            map_location="cpu",
            weights_only=True,
        )
    )
    model.eval()

    # 4. คำนวณ Reconstruction Error ของ Normal Validation
    normal_mask = train_targets["is_attack"].eq(0)
    normal_features = train_features.loc[normal_mask]

    _, X_val = train_test_split(
        normal_features,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    X_val_scaled = scaler.transform(X_val[feature_columns])
    val_tensor = torch.tensor(X_val_scaled, dtype=torch.float32)

    with torch.no_grad():
        val_reconstructed = model(val_tensor)
        val_errors = (
            (val_tensor - val_reconstructed) ** 2
        ).mean(dim=1).numpy()

    # 5. คำนวณ Reconstruction Error ของ KDDTest
    X_test_scaled = scaler.transform(
        test_features[feature_columns]
    )
    test_tensor = torch.tensor(
        X_test_scaled, dtype=torch.float32
    )

    with torch.no_grad():
        test_reconstructed = model(test_tensor)
        test_errors = (
            (test_tensor - test_reconstructed) ** 2
        ).mean(dim=1).numpy()

    # 6. เตรียม Label และกลุ่มย่อย
    train_labels = set(
        train_targets.loc[
            train_targets["is_attack"].eq(1), "label"
        ].astype(str).str.strip().str.lower()
    )

    test_labels = (
        test_targets["label"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    is_attack = test_targets["is_attack"].eq(1).to_numpy()
    y_test = is_attack.astype(int)

    is_unseen = is_attack & ~test_labels.isin(train_labels).to_numpy()

    difficult_labels = [
        "snmpguess",
        "snmpgetattack",
        "mailbomb",
    ]

    is_difficult = (
        is_unseen
        & test_labels.isin(difficult_labels).to_numpy()
    )

    # 7. ทดสอบหลายระดับ Percentile
    percentiles = [90, 95, 97, 98, 99]
    records = []

    print("=== Threshold Comparison across Groups ===")

    for p in percentiles:
        threshold = float(np.percentile(val_errors, p))

        # ตรวจสอบกับ Normal Validation
        val_pred = (val_errors > threshold).astype(int)
        val_fpr = val_pred.mean()

        # ตรวจสอบกับ KDDTest ภาพรวม
        test_pred = (test_errors > threshold).astype(int)
        acc = accuracy_score(y_test, test_pred)
        prec = precision_score(
            y_test, test_pred, zero_division=0
        )
        rec = recall_score(
            y_test, test_pred, zero_division=0
        )
        f1 = f1_score(y_test, test_pred, zero_division=0)

        tn, fp, fn, tp = confusion_matrix(
            y_test, test_pred, labels=[0, 1]
        ).ravel()
        test_fpr = fp / (fp + tn) if (fp + tn) else 0.0

        # ตรวจสอบกับกลุ่มย่อย
        unseen_recall = (
            test_pred[is_unseen].mean()
            if np.any(is_unseen)
            else 0.0
        )
        difficult_recall = (
            test_pred[is_difficult].mean()
            if np.any(is_difficult)
            else 0.0
        )

        records.append({
            "percentile": f"P{p}",
            "threshold": threshold,
            "val_fpr": val_fpr,
            "test_fpr": test_fpr,
            "accuracy": acc,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "unseen_recall": unseen_recall,
            "difficult_recall": difficult_recall,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        })

        print(
            f"\n--- P{p} (Threshold: {threshold:.6f}) ---"
        )
        print(f"Validation FPR:   {val_fpr:.4f}")
        print(f"Test FPR:         {test_fpr:.4f}")
        print(f"Test F1-score:    {f1:.4f}")
        print(f"Test Recall:      {rec:.4f}")
        print(f"Unseen Recall:    {unseen_recall:.4f}")
        print(f"Difficult Recall: {difficult_recall:.4f}")

    # 8. บันทึกผลลัพธ์
    results = pd.DataFrame(records)

    output_path = CSV_DIR / "threshold_group_comparison.csv"
    results.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"\nSaved report: {output_path}")


if __name__ == "__main__":
    main()
