import argparse
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.autoencoder.autoencoder_model import Autoencoder

DATA_DIR = (
    PROJECT_ROOT
    / "data-pipeline"
    / "output"
    / "NSL-KDD"
    / "feature_engineered"
)

MODEL_DIR = PROJECT_ROOT / "model" / "autoencoder"


def main():
    parser = argparse.ArgumentParser(description="ประเมินการตรวจจับ Known และ Unseen Attacks ของ Autoencoder")
    parser.add_argument(
        "--dataset",
        type=str,
        default="KDDTest",
        choices=["KDDTest", "KDDTest-21"],
        help="ชุดข้อมูลที่ต้องการประเมิน (KDDTest หรือ KDDTest-21)",
    )
    parser.add_argument(
        "--percentile",
        type=float,
        default=95.0,
        help="เปอร์เซ็นไทล์สำหรับกำหนด Threshold (default: 95.0)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="อุปกรณ์ (auto, cuda, cpu)",
    )
    args = parser.parse_args()

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    # 1. โหลดข้อมูลและโมเดล
    train_features = pd.read_csv(DATA_DIR / "KDDTrain_features.csv")
    train_targets = pd.read_csv(DATA_DIR / "KDDTrain_targets.csv")

    test_features = pd.read_csv(DATA_DIR / f"{args.dataset}_features.csv")
    test_targets = pd.read_csv(DATA_DIR / f"{args.dataset}_targets.csv")

    assert len(train_features) == len(train_targets), "จำนวนแถว Train Features และ Targets ไม่ตรงกัน"
    assert len(test_features) == len(test_targets), "จำนวนแถว Test Features และ Targets ไม่ตรงกัน"

    scaler = joblib.load(MODEL_DIR / "scaler.pkl")
    feature_columns = (MODEL_DIR / "feature_columns.txt").read_text(encoding="utf-8").splitlines()

    missing_train = set(feature_columns) - set(train_features.columns)
    missing_test = set(feature_columns) - set(test_features.columns)

    if missing_train or missing_test:
        raise ValueError(
            f"Missing train features: {sorted(missing_train)}\n"
            f"Missing test features: {sorted(missing_test)}"
        )

    model = Autoencoder(input_dim=len(feature_columns)).to(device)
    model.load_state_dict(
        torch.load(
            MODEL_DIR / "autoencoder.pth",
            map_location=device,
            weights_only=True,
        )
    )
    model.eval()

    # 2. หา Threshold จาก Normal Validation
    normal_train_mask = train_targets["is_attack"].eq(0)
    normal_features = train_features.loc[normal_train_mask]

    _, X_val = train_test_split(
        normal_features,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    X_val = X_val[feature_columns]
    X_val_scaled = scaler.transform(X_val)
    val_tensor = torch.tensor(X_val_scaled, dtype=torch.float32).to(device)

    with torch.no_grad():
        val_reconstructed = model(val_tensor)
        val_errors = ((val_tensor - val_reconstructed) ** 2).mean(dim=1).cpu().numpy()

    threshold = float(np.percentile(val_errors, args.percentile))

    # 3. ระบุ Known และ Unseen Attack
    train_labels = (
        train_targets["label"].astype(str).str.strip().str.lower()
    )
    test_labels = (
        test_targets["label"].astype(str).str.strip().str.lower()
    )

    known_labels = set(train_labels[train_targets["is_attack"].eq(1)])
    is_attack = test_targets["is_attack"].eq(1)
    is_normal = ~is_attack

    known_mask = is_attack & test_labels.isin(known_labels)
    unseen_mask = is_attack & ~test_labels.isin(known_labels)

    print("=" * 60)
    print(f"AUTOENCODER - UNKNOWN ATTACK EVALUATION ({args.dataset})")
    print("=" * 60)
    print(f"Number of features:   {len(feature_columns)}")
    print(f"Threshold (P{args.percentile}):      {threshold:.6f}")
    print(f"Normal test records:  {int(is_normal.sum()):,}")
    print(f"Known attack records: {int(known_mask.sum()):,}")
    print(f"Unseen attack records:{int(unseen_mask.sum()):,}")

    print("\n=== Unseen Attack Labels ===")
    unseen_label_counts = test_labels[unseen_mask].value_counts()
    if unseen_label_counts.empty:
        print("No unseen attack labels found.")
    else:
        print(unseen_label_counts.to_string())

    # 4. คำนวณ Reconstruction Error
    X_test = test_features[feature_columns]
    X_test_scaled = scaler.transform(X_test)
    test_tensor = torch.tensor(X_test_scaled, dtype=torch.float32).to(device)

    with torch.no_grad():
        reconstructed = model(test_tensor)
        test_errors = ((test_tensor - reconstructed) ** 2).mean(dim=1).cpu().numpy()

    predictions = (test_errors > threshold).astype(int)

    # 5. ประเมินผลภาพรวม
    y_true = test_targets["is_attack"].astype(int).to_numpy()
    tn, fp, fn, tp = confusion_matrix(y_true, predictions, labels=[0, 1]).ravel()
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    print("\n" + "=" * 60)
    print(f"OVERALL EVALUATION ({args.dataset})")
    print("=" * 60)
    print(f"Total records:        {len(y_true):,}")
    print(f"Accuracy:             {accuracy_score(y_true, predictions):.4f}")
    print(f"Precision:            {precision_score(y_true, predictions, zero_division=0):.4f}")
    print(f"Recall:               {recall_score(y_true, predictions, zero_division=0):.4f}")
    print(f"F1-score:             {f1_score(y_true, predictions, zero_division=0):.4f}")
    print(f"False Positive Rate:  {fpr:.4f}")

    print("\nConfusion Matrix:")
    print(f"TN (Normal correct):  {tn:,}")
    print(f"FP (Normal flagged):  {fp:,}")
    print(f"FN (Attack missed):   {fn:,}")
    print(f"TP (Attack detected): {tp:,}")

    # 6. ประเมิน Known vs Unseen
    def report_attack_group(name, mask):
        group_predictions = predictions[mask.to_numpy()]
        total = int(mask.sum())
        detected = int((group_predictions == 1).sum())
        missed = int((group_predictions == 0).sum())
        detection_rate = detected / total if total else 0.0

        print(f"\n=== {name} ===")
        print(f"Total attacks:  {total:,}")
        print(f"Detected:       {detected:,}")
        print(f"Missed:         {missed:,}")
        print(f"Detection Rate: {detection_rate:.4f}")

    report_attack_group("Known Attack", known_mask)
    report_attack_group("Unseen Attack", unseen_mask)

    # 7. สรุปผลแยกตาม Attack Label
    results = test_targets[["label", "attack_family"]].copy()
    results["label_normalized"] = test_labels.to_numpy()
    results["is_attack"] = y_true
    results["predicted_attack"] = predictions
    results["reconstruction_error"] = test_errors
    results["attack_group"] = "Normal"

    results.loc[known_mask.to_numpy(), "attack_group"] = "Known"
    results.loc[unseen_mask.to_numpy(), "attack_group"] = "Unseen"

    attack_results = results[results["is_attack"] == 1].copy()

    summary = attack_results.groupby(
        ["label", "attack_family", "attack_group"],
        dropna=False,
    ).agg(
        total=("predicted_attack", "size"),
        detected=("predicted_attack", "sum"),
        mean_reconstruction_error=("reconstruction_error", "mean"),
    )

    summary["missed"] = summary["total"] - summary["detected"]
    summary["detection_rate"] = summary["detected"] / summary["total"]
    summary = summary.sort_values(["detection_rate", "total"])

    print("\n" + "=" * 60)
    print("DETECTION RATE BY ATTACK LABEL")
    print("=" * 60)
    print(summary.to_string())

    # 8. บันทึกผลลัพธ์
    CSV_DIR = MODEL_DIR / "results" / "csv"
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.dataset.lower()}"

    summary_path = MODEL_DIR / f"unseen_attack_results{suffix}.csv"
    summary.to_csv(summary_path, encoding="utf-8-sig")
    summary.to_csv(CSV_DIR / f"unseen_attack_results{suffix}.csv", encoding="utf-8-sig")
    summary.to_csv(CSV_DIR / "unseen_attack_results.csv", encoding="utf-8-sig")
    summary.to_csv(MODEL_DIR / "unseen_attack_results.csv", encoding="utf-8-sig")

    detail_path = MODEL_DIR / f"unseen_attack_details{suffix}.csv"
    results.to_csv(detail_path, index=False, encoding="utf-8-sig")
    results.to_csv(CSV_DIR / f"unseen_attack_details{suffix}.csv", index=False, encoding="utf-8-sig")
    results.to_csv(CSV_DIR / "unseen_attack_details.csv", index=False, encoding="utf-8-sig")
    results.to_csv(MODEL_DIR / "unseen_attack_details.csv", index=False, encoding="utf-8-sig")

    print("\n=== Saved Reports ===")
    print(f"Attack summary: {summary_path}")
    print(f"Record details: {detail_path}")


if __name__ == "__main__":
    main()
