import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score,
    classification_report,
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

# ตำแหน่งชุดข้อมูลและโมเดล
DATA_DIR = (
    PROJECT_ROOT
    / "data-pipeline"
    / "output"
    / "NSL-KDD"
    / "feature_engineered"
)

MODEL_DIR = PROJECT_ROOT / "model" / "autoencoder"


def main():
    parser = argparse.ArgumentParser(description="ประเมินโมเดล Autoencoder บนชุดทดสอบ NSL-KDD")
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
        help="เปอร์เซ็นไทล์จาก Validation Error สำหรับกำหนด Threshold (default: 95.0)",
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

    print("=== Load Model and Dataset ===")
    print(f"Dataset: {args.dataset} | Device: {device}")

    # โหลดชุดข้อมูล
    train_features = pd.read_csv(DATA_DIR / "KDDTrain_features.csv")
    train_targets = pd.read_csv(DATA_DIR / "KDDTrain_targets.csv")

    test_features = pd.read_csv(DATA_DIR / f"{args.dataset}_features.csv")
    test_targets = pd.read_csv(DATA_DIR / f"{args.dataset}_targets.csv")

    scaler = joblib.load(MODEL_DIR / "scaler.pkl")

    feature_columns = (
        (MODEL_DIR / "feature_columns.txt").read_text(encoding="utf-8").splitlines()
    )

    print(f"Test features:  {test_features.shape}")
    print(f"Test targets:   {test_targets.shape}")
    print(f"Model features: {len(feature_columns)}")

    # ตรวจสอบฟีเจอร์ที่ขาดหาย
    missing_cols = set(feature_columns) - set(test_features.columns)
    if missing_cols:
        raise ValueError(f"ฟีเจอร์ใน Test ไม่ครบตามที่โมเดลต้องการ: {missing_cols}")

    # 3. เตรียมข้อมูล Validation สำหรับหา Threshold
    normal_mask = train_targets["is_attack"].eq(0)
    normal_features = train_features.loc[normal_mask]

    _, X_val = train_test_split(
        normal_features,
        test_size=0.20,
        random_state=42,
        shuffle=True,
    )

    X_val = X_val[feature_columns]
    X_val_scaled = scaler.transform(X_val)
    val_tensor = torch.tensor(X_val_scaled, dtype=torch.float32).to(device)

    model = Autoencoder(input_dim=len(feature_columns)).to(device)
    model.load_state_dict(
        torch.load(
            MODEL_DIR / "autoencoder.pth",
            map_location=device,
            weights_only=True,
        )
    )
    model.eval()

    with torch.no_grad():
        val_reconstructed = model(val_tensor)
        val_errors = torch.mean((val_tensor - val_reconstructed) ** 2, dim=1).cpu().numpy()

    threshold = float(np.percentile(val_errors, args.percentile))

    print("\n=== Threshold ===")
    print(f"Threshold (Percentile {args.percentile}%): {threshold:.6f}")

    # 4. ทดสอบข้อมูล Test
    X_test = test_features[feature_columns]
    y_test = test_targets["is_attack"].astype(int).to_numpy()

    X_test_scaled = scaler.transform(X_test)
    test_tensor = torch.tensor(X_test_scaled, dtype=torch.float32).to(device)

    with torch.no_grad():
        test_reconstructed = model(test_tensor)
        test_errors = torch.mean((test_tensor - test_reconstructed) ** 2, dim=1).cpu().numpy()

    y_pred = (test_errors > threshold).astype(int)

    # 5. แสดงผลการประเมิน
    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    tn, fp, fn, tp = confusion_matrix(y_test, y_pred, labels=[0, 1]).ravel()
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    print(f"\n=== Evaluation Results ({args.dataset}) ===")
    print(f"Accuracy:  {acc:.4f}")
    print(f"Precision: {prec:.4f}")
    print(f"Recall:    {rec:.4f}")
    print(f"F1-score:  {f1:.4f}")
    print(f"False Positive Rate: {fpr:.4f}")

    print("\n=== Confusion Matrix ===")
    print(f"True Normal (TN):    {tn}")
    print(f"False Attack (FP):   {fp}")
    print(f"Missed Attack (FN):  {fn}")
    print(f"Detected Attack (TP):{tp}")

    print("\n=== Classification Report ===")
    print(
        classification_report(
            y_test,
            y_pred,
            target_names=["Normal", "Attack"],
            zero_division=0,
        )
    )


if __name__ == "__main__":
    main()
