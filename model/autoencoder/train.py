import argparse
import copy
import random
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

# ตำแหน่งหลักของโปรเจกต์
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.autoencoder.autoencoder_model import Autoencoder

# ตำแหน่งชุดข้อมูล
DATA_DIR = (
    PROJECT_ROOT
    / "data-pipeline"
    / "output"
    / "NSL-KDD"
    / "feature_engineered"
)


def set_seed(seed: int = 42):
    """กำหนด random seed เพื่อความแม่นยำและการทำซ้ำได้ (Reproducibility)"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_dataset(name: str):
    """โหลด Features และ Targets ของชุดข้อมูลที่กำหนด"""
    features_path = DATA_DIR / f"{name}_features.csv"
    targets_path = DATA_DIR / f"{name}_targets.csv"

    if not features_path.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์: {features_path}")

    if not targets_path.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์: {targets_path}")

    features = pd.read_csv(features_path)
    targets = pd.read_csv(targets_path)

    if len(features) != len(targets):
        raise ValueError(
            f"{name}: จำนวน Features ({len(features)}) "
            f"ไม่ตรงกับ Targets ({len(targets)})"
        )

    if "is_attack" not in targets.columns:
        raise ValueError("ไม่พบคอลัมน์ is_attack ใน Targets")

    return features, targets


def prepare_normal_data(features, targets, test_size=0.20, seed=42):
    """แบ่งข้อมูล Normal เป็น Training และ Validation"""
    normal_mask = targets["is_attack"].eq(0)
    X_normal = features.loc[normal_mask].copy()

    X_train, X_val = train_test_split(
        X_normal,
        test_size=test_size,
        random_state=seed,
        shuffle=True,
    )

    return X_train, X_val


def remove_constant_columns(X_train, X_val):
    """ตัดคอลัมน์คงที่โดยอ้างอิงจาก Training Data"""
    constant_columns = X_train.columns[
        X_train.nunique() <= 1
    ]

    X_train = X_train.drop(columns=constant_columns)
    X_val = X_val.drop(columns=constant_columns)

    return X_train, X_val, constant_columns.tolist()


def scale_data(X_train, X_val):
    """ปรับสเกลโดยเรียนรู้จาก Training Data เท่านั้น"""
    scaler = StandardScaler()

    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)

    return X_train_scaled, X_val_scaled, scaler


def train_model(
    X_train_scaled,
    X_val_scaled,
    epochs=25,
    batch_size=256,
    lr=0.001,
    device="cpu",
):
    """ฝึก Autoencoder ด้วยข้อมูล Normal เท่านั้น และเก็บบันทึกน้ำหนักที่ดีที่สุด"""
    train_tensor = torch.tensor(
        X_train_scaled,
        dtype=torch.float32,
    )
    val_tensor = torch.tensor(
        X_val_scaled,
        dtype=torch.float32,
    ).to(device)

    train_dataset = TensorDataset(train_tensor)
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
    )

    input_dim = X_train_scaled.shape[1]
    model = Autoencoder(input_dim=input_dim).to(device)

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=lr,
    )

    history = []
    best_val_loss = float("inf")
    best_model_weights = None
    best_epoch = 1

    for epoch in range(epochs):
        model.train()
        total_train_loss = 0.0

        for (batch,) in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad()

            reconstructed = model(batch)
            loss = criterion(reconstructed, batch)

            loss.backward()
            optimizer.step()

            total_train_loss += loss.item() * batch.size(0)

        train_loss = total_train_loss / len(train_dataset)

        model.eval()
        total_val_loss = 0.0

        with torch.no_grad():
            for start in range(0, len(val_tensor), batch_size):
                batch = val_tensor[start : start + batch_size]
                reconstructed = model(batch)
                loss = criterion(reconstructed, batch)
                total_val_loss += loss.item() * batch.size(0)

        val_loss = total_val_loss / len(val_tensor)

        history.append({
            "epoch": epoch + 1,
            "train_loss": train_loss,
            "val_loss": val_loss,
        })

        is_best = ""
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model_weights = copy.deepcopy(model.state_dict())
            best_epoch = epoch + 1
            is_best = " (Best)"

        print(
            f"Epoch [{epoch + 1:02d}/{epochs:02d}] "
            f"Train Loss: {train_loss:.6f} | "
            f"Val Loss: {val_loss:.6f}{is_best}"
        )

    if best_model_weights is not None:
        model.load_state_dict(best_model_weights)
        print(f"\nโหลดน้ำหนักโมเดลที่ดีที่สุดจาก Epoch {best_epoch} (Val Loss: {best_val_loss:.6f})")

    return model, history


def evaluate_on_test(model, scaler, feature_columns, val_scaled, threshold_percentile=95.0, device="cpu"):
    """หา Threshold จาก Validation และทดสอบบน KDDTest"""
    print("\n=== Evaluating on KDDTest ===")
    test_features, test_targets = load_dataset("KDDTest")

    # 1. คำนวณ Threshold จาก Validation
    val_tensor = torch.tensor(val_scaled, dtype=torch.float32).to(device)
    model.eval()
    with torch.no_grad():
        val_reconstructed = model(val_tensor)
        val_errors = torch.mean((val_tensor - val_reconstructed) ** 2, dim=1).cpu().numpy()

    threshold = float(np.percentile(val_errors, threshold_percentile))
    print(f"Threshold (Percentile {threshold_percentile}%): {threshold:.6f}")

    # 2. ปรับสเกลและส่งข้อมูล Test เข้าโมเดล
    X_test = test_features[feature_columns]
    y_test = test_targets["is_attack"].astype(int).to_numpy()
    X_test_scaled = scaler.transform(X_test)
    test_tensor = torch.tensor(X_test_scaled, dtype=torch.float32).to(device)

    with torch.no_grad():
        test_reconstructed = model(test_tensor)
        test_errors = torch.mean((test_tensor - test_reconstructed) ** 2, dim=1).cpu().numpy()

    y_pred = (test_errors > threshold).astype(int)

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    tn, fp, fn, tp = confusion_matrix(y_test, y_pred, labels=[0, 1]).ravel()
    fpr = fp / (fp + tn) if (fp + tn) else 0.0

    print(f"Accuracy:  {acc:.4f}")
    print(f"Precision: {prec:.4f}")
    print(f"Recall:    {rec:.4f}")
    print(f"F1-score:  {f1:.4f}")
    print(f"FPR:       {fpr:.4f}")
    print(f"Confusion Matrix: TN={tn}, FP={fp}, FN={fn}, TP={tp}")


def main():
    parser = argparse.ArgumentParser(description="ฝึกโมเดล Autoencoder สำหรับตรวจจับ Anomaly บน NSL-KDD")
    parser.add_argument("--epochs", type=int, default=25, help="จำนวนรอบในการฝึก (default: 25)")
    parser.add_argument("--batch-size", type=int, default=256, help="ขนาด Batch size (default: 256)")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate (default: 0.001)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--val-size", type=float, default=0.20, help="สัดส่วน Validation split (default: 0.20)")
    parser.add_argument("--threshold-percentile", type=float, default=95.0, help="เปอร์เซ็นไทล์สำหรับ Threshold (default: 95.0)")
    parser.add_argument("--skip-eval", action="store_true", help="ข้ามขั้นตอนประเมินผลบนชุดทดสอบหลังฝึก")
    parser.add_argument("--device", type=str, default="auto", help="อุปกรณ์ที่ใช้ (auto, cuda, cpu)")

    args = parser.parse_args()

    # เลือก Device
    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    set_seed(args.seed)
    print(f"กำลังใช้อุปกรณ์: {device} | Seed: {args.seed}")

    # 1. โหลดข้อมูล
    features, targets = load_dataset("KDDTrain")

    normal_count = int((targets["is_attack"] == 0).sum())
    attack_count = int((targets["is_attack"] == 1).sum())

    print("\n=== NSL-KDD Dataset Check ===")
    print(f"Features shape:  {features.shape}")
    print(f"Targets shape:   {targets.shape}")
    print(f"Normal records:  {normal_count:,}")
    print(f"Attack records:  {attack_count:,}")

    # 2. แบ่งข้อมูล Normal
    X_train, X_val = prepare_normal_data(
        features, targets, test_size=args.val_size, seed=args.seed
    )

    print("\n=== Normal Data Split ===")
    print(f"Train shape:      {X_train.shape}")
    print(f"Validation shape: {X_val.shape}")

    # 3. ตัดคอลัมน์คงที่
    X_train, X_val, constant_columns = remove_constant_columns(X_train, X_val)

    print("\n=== Constant Column Removal ===")
    print(f"Removed columns:   {len(constant_columns)}")
    print(f"Remaining columns: {X_train.shape[1]}")

    # 4. ปรับสเกลข้อมูล
    X_train_scaled, X_val_scaled, scaler = scale_data(X_train, X_val)

    print("\n=== Feature Scaling ===")
    print(f"Train scaled shape:      {X_train_scaled.shape}")
    print(f"Validation scaled shape: {X_val_scaled.shape}")

    # 5. ฝึก Autoencoder
    print("\n=== Autoencoder Training ===")
    model, history = train_model(
        X_train_scaled,
        X_val_scaled,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        device=device,
    )

    # 6. บันทึกโมเดลและองค์ประกอบที่ใช้เตรียมข้อมูล
    model_dir = PROJECT_ROOT / "model" / "autoencoder"
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "autoencoder.pth"
    torch.save(model.state_dict(), model_path)

    scaler_path = model_dir / "scaler.pkl"
    joblib.dump(scaler, scaler_path)

    columns_path = model_dir / "feature_columns.txt"
    columns_path.write_text(
        "\n".join(X_train.columns),
        encoding="utf-8",
    )

    history_df = pd.DataFrame(history)
    history_path = model_dir / "training_history.csv"
    history_df.to_csv(history_path, index=False)

    print("\n=== Save Artifacts ===")
    print(f"Model saved:    {model_path}")
    print(f"Scaler saved:   {scaler_path}")
    print(f"Features saved: {columns_path} ({len(X_train.columns)} features)")
    print(f"History saved:  {history_path}")

    # 7. ประเมินผลบน Test Set
    if not args.skip_eval:
        evaluate_on_test(
            model=model,
            scaler=scaler,
            feature_columns=list(X_train.columns),
            val_scaled=X_val_scaled,
            threshold_percentile=args.threshold_percentile,
            device=device,
        )


if __name__ == "__main__":
    main()
