import os
import sys
import random
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix
)

import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader

# -------------------------------------------------------------
# Configuration and Reproducibility
# -------------------------------------------------------------
def seed_everything(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

ATTACK_FAMILY_MAP = {
    # Train set attack types
    "back": "DoS", "land": "DoS", "neptune": "DoS", "pod": "DoS", "smurf": "DoS", "teardrop": "DoS",
    "ipsweep": "Probe", "nmap": "Probe", "portsweep": "Probe", "satan": "Probe",
    "ftp_write": "R2L", "guess_passwd": "R2L", "imap": "R2L", "multihop": "R2L", "phf": "R2L",
    "spy": "R2L", "warezclient": "R2L", "warezmaster": "R2L",
    "buffer_overflow": "U2R", "loadmodule": "U2R", "perl": "U2R", "rootkit": "U2R",
    # Test set novel attack types (Academic benchmark standard)
    "apache2": "DoS", "mailbomb": "DoS", "processtable": "DoS", "udpstorm": "DoS", "worm": "DoS",
    "mscan": "Probe", "saint": "Probe",
    "snmpguess": "R2L", "snmpgetattack": "R2L", "httptunnel": "R2L", "named": "R2L", "sendmail": "R2L",
    "xlock": "R2L", "xsnoop": "R2L",
    "ps": "U2R", "xterm": "U2R", "sqlattack": "U2R"
}

# -------------------------------------------------------------
# PyTorch MLP Architecture
# -------------------------------------------------------------
class NSL_MLP(nn.Module):
    def __init__(self, input_dim, num_classes, dropout_rate=0.3):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(dropout_rate * 0.7),
            
            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Dropout(dropout_rate * 0.5),
            
            nn.Linear(32, num_classes)
        )
        
    def forward(self, x):
        return self.net(x)

# -------------------------------------------------------------
# Training and Evaluation Functions
# -------------------------------------------------------------
def train_epoch(model, loader, criterion, optimizer, device):
    model.train()
    total_loss = 0.0
    all_preds, all_targets = [], []
    
    for x_batch, y_batch in loader:
        x_batch, y_batch = x_batch.to(device), y_batch.to(device)
        optimizer.zero_grad()
        logits = model(x_batch)
        loss = criterion(logits, y_batch)
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item() * len(y_batch)
        preds = torch.argmax(logits, dim=1).detach().cpu().numpy()
        all_preds.extend(preds)
        all_targets.extend(y_batch.cpu().numpy())
        
    epoch_loss = total_loss / len(loader.dataset)
    epoch_acc = accuracy_score(all_targets, all_preds)
    _, _, epoch_f1, _ = precision_recall_fscore_support(all_targets, all_preds, average='macro', zero_division=0)
    return epoch_loss, epoch_acc, epoch_f1

def evaluate_model(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    all_preds, all_targets = [], []
    
    with torch.no_grad():
        for x_batch, y_batch in loader:
            x_batch, y_batch = x_batch.to(device), y_batch.to(device)
            logits = model(x_batch)
            loss = criterion(logits, y_batch)
            total_loss += loss.item() * len(y_batch)
            
            preds = torch.argmax(logits, dim=1).cpu().numpy()
            all_preds.extend(preds)
            all_targets.extend(y_batch.cpu().numpy())
            
    eval_loss = total_loss / len(loader.dataset)
    all_preds = np.array(all_preds)
    all_targets = np.array(all_targets)
    return eval_loss, all_preds, all_targets

# -------------------------------------------------------------
# Main Experiment Runner
# -------------------------------------------------------------
def run_experiment(task="multiclass", epochs=30, batch_size=256, lr=1e-3, seed=42):
    seed_everything(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n=======================================================")
    print(f" Starting Experiment: Task = {task.upper()} (Device: {device})")
    print(f"=======================================================")
    
    script_dir = Path(__file__).resolve().parent
    data_dir = script_dir.parent.parent / "data-pipeline" / "output" / "NSL-KDD" / "feature_engineered"
    plots_dir = script_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Load Data
    print("Loading feature-engineered datasets...")
    X_train_df = pd.read_csv(data_dir / "KDDTrain_features.csv")
    y_train_df = pd.read_csv(data_dir / "KDDTrain_targets.csv")
    
    X_test_df = pd.read_csv(data_dir / "KDDTest_features.csv")
    y_test_df = pd.read_csv(data_dir / "KDDTest_targets.csv")
    
    X_test21_df = pd.read_csv(data_dir / "KDDTest-21_features.csv")
    y_test21_df = pd.read_csv(data_dir / "KDDTest-21_targets.csv")
    
    # 2. Setup Targets
    if task == "binary":
        target_col = "is_attack"
        y_train_raw = y_train_df[target_col].values
        y_test_raw = y_test_df[target_col].values
        y_test21_raw = y_test21_df[target_col].values
        class_names = ["Normal", "Attack"]
        le = None
        y_train = y_train_raw
        y_test = y_test_raw
        y_test21 = y_test21_raw
    else:
        # Multiclass: Map all attacks (including novel ones) to standard 5 families
        def map_family(row):
            lbl = str(row["label"]).strip().lower()
            if lbl == "normal":
                return "Normal"
            return ATTACK_FAMILY_MAP.get(lbl, "Unknown")
            
        y_train_raw = y_train_df.apply(map_family, axis=1).values
        y_test_raw = y_test_df.apply(map_family, axis=1).values
        y_test21_raw = y_test21_df.apply(map_family, axis=1).values
        
        class_names = ["Normal", "DoS", "Probe", "R2L", "U2R"]
        le = LabelEncoder()
        le.fit(class_names)
        y_train = le.transform(y_train_raw)
        y_test = le.transform(y_test_raw)
        y_test21 = le.transform(y_test21_raw)
        
    num_classes = len(class_names)
    print(f"Target classes ({num_classes}): {class_names}")
    
    # 3. Stratified Train / Validation Split (80 / 20)
    X_tr, X_val, y_tr, y_val = train_test_split(
        X_train_df.values, y_train, test_size=0.2, random_state=seed, stratify=y_train
    )
    
    # 4. Fit StandardScaler strictly on Train split
    print("Fitting StandardScaler on training split (no data leakage)...")
    scaler = StandardScaler()
    X_tr = scaler.fit_transform(X_tr)
    X_val = scaler.transform(X_val)
    X_test = scaler.transform(X_test_df.values)
    X_test21 = scaler.transform(X_test21_df.values)
    
    input_dim = X_tr.shape[1]
    print(f"Input dimensions: {input_dim} features | Training samples: {len(X_tr)} | Validation samples: {len(X_val)}")
    
    # 5. Compute Class Weights for Imbalance Handling (Smooth Square Root)
    class_counts = np.bincount(y_tr, minlength=num_classes)
    total_samples = len(y_tr)
    # Smooth weight formula: sqrt(N / (K * count_c)) to avoid gradient explosion on tiny classes (e.g., U2R)
    smoothed_weights = np.sqrt(total_samples / (num_classes * np.maximum(class_counts, 1)))
    smoothed_weights = smoothed_weights / np.mean(smoothed_weights) # normalize around 1.0
    weight_tensor = torch.tensor(smoothed_weights, dtype=torch.float32).to(device)
    
    print("\nClass distribution in Training split:")
    for i, cname in enumerate(class_names):
        print(f"  - {cname:7s}: {class_counts[i]:6d} ({class_counts[i]/total_samples*100:5.2f}%) | Weight: {smoothed_weights[i]:.3f}")
        
    criterion = nn.CrossEntropyLoss(weight=weight_tensor)
    
    # 6. Create DataLoaders
    train_dataset = TensorDataset(torch.tensor(X_tr, dtype=torch.float32), torch.tensor(y_tr, dtype=torch.long))
    val_dataset = TensorDataset(torch.tensor(X_val, dtype=torch.float32), torch.tensor(y_val, dtype=torch.long))
    test_dataset = TensorDataset(torch.tensor(X_test, dtype=torch.float32), torch.tensor(y_test, dtype=torch.long))
    test21_dataset = TensorDataset(torch.tensor(X_test21, dtype=torch.float32), torch.tensor(y_test21, dtype=torch.long))
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)
    test21_loader = DataLoader(test21_dataset, batch_size=batch_size, shuffle=False)
    
    # 7. Initialize Model, Optimizer, Scheduler
    model = NSL_MLP(input_dim=input_dim, num_classes=num_classes, dropout_rate=0.3).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='max', factor=0.5, patience=3)
    
    # 8. Training Loop with Early Stopping
    best_val_f1 = -1.0
    best_model_path = script_dir / f"best_mlp_{task}.pth"
    history = {"train_loss": [], "val_loss": [], "train_f1": [], "val_f1": []}
    
    print(f"\nTraining MLP for {epochs} epochs...")
    for epoch in range(1, epochs + 1):
        tr_loss, tr_acc, tr_f1 = train_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_preds, val_targets = evaluate_model(model, val_loader, criterion, device)
        
        val_acc = accuracy_score(val_targets, val_preds)
        _, _, val_f1, _ = precision_recall_fscore_support(val_targets, val_preds, average='macro', zero_division=0)
        
        scheduler.step(val_f1)
        
        history["train_loss"].append(tr_loss)
        history["val_loss"].append(val_loss)
        history["train_f1"].append(tr_f1)
        history["val_f1"].append(val_f1)
        
        improved = ""
        if val_f1 > best_val_f1:
            best_val_f1 = val_f1
            torch.save(model.state_dict(), best_model_path)
            improved = " [SAVED BEST]"
            
        print(f"Epoch {epoch:2d}/{epochs:2d} | Train Loss: {tr_loss:.4f} Acc: {tr_acc*100:.2f}% F1: {tr_f1:.4f} | "
              f"Val Loss: {val_loss:.4f} Acc: {val_acc*100:.2f}% F1: {val_f1:.4f}{improved}")
              
    print(f"\nLoading best model checkpoint with Val Macro F1: {best_val_f1:.4f}")
    model.load_state_dict(torch.load(best_model_path, map_location=device))
    
    # 9. Final Evaluation on KDDTest+ and KDDTest-21
    def get_metrics_dict(preds, targets, name):
        acc = accuracy_score(targets, preds)
        bal_acc = balanced_accuracy_score(targets, preds)
        p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(targets, preds, average='macro', zero_division=0)
        p_wt, r_wt, f1_wt, _ = precision_recall_fscore_support(targets, preds, average='weighted', zero_division=0)
        report = classification_report(targets, preds, target_names=class_names, output_dict=True, zero_division=0)
        cm = confusion_matrix(targets, preds)
        return {
            "name": name,
            "accuracy": float(acc),
            "balanced_accuracy": float(bal_acc),
            "macro_precision": float(p_macro),
            "macro_recall": float(r_macro),
            "macro_f1": float(f1_macro),
            "weighted_f1": float(f1_wt),
            "classification_report": report,
            "confusion_matrix": cm.tolist()
        }
        
    _, test_preds, test_targets = evaluate_model(model, test_loader, criterion, device)
    _, test21_preds, test21_targets = evaluate_model(model, test21_loader, criterion, device)
    
    test_metrics = get_metrics_dict(test_preds, test_targets, "KDDTest+")
    test21_metrics = get_metrics_dict(test21_preds, test21_targets, "KDDTest-21")
    
    # 10. Print Comprehensive Reports
    for m in [test_metrics, test21_metrics]:
        print(f"\n=======================================================")
        print(f" Evaluation Report: {m['name']} ({task.upper()})")
        print(f"=======================================================")
        print(f"Accuracy:          {m['accuracy']*100:.2f}%")
        print(f"Balanced Accuracy: {m['balanced_accuracy']*100:.2f}%")
        print(f"Macro F1-Score:    {m['macro_f1']:.4f}")
        print(f"Macro Recall:      {m['macro_recall']:.4f}")
        print("\nDetailed Per-Class Performance:")
        rep_df = pd.DataFrame(m["classification_report"]).transpose()
        print(rep_df[["precision", "recall", "f1-score", "support"]].to_string())
        
    # 11. Plotting Curves & Confusion Matrices
    # Plot A: Loss and F1 curves
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].plot(range(1, epochs + 1), history["train_loss"], label="Train Loss", marker='o')
    axes[0].plot(range(1, epochs + 1), history["val_loss"], label="Val Loss", marker='s')
    axes[0].set_title(f"MLP Loss Curve ({task.capitalize()})")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].legend()
    axes[0].grid(True, linestyle="--", alpha=0.5)
    
    axes[1].plot(range(1, epochs + 1), history["train_f1"], label="Train Macro F1", marker='o')
    axes[1].plot(range(1, epochs + 1), history["val_f1"], label="Val Macro F1", marker='s')
    axes[1].set_title(f"MLP Macro F1 Curve ({task.capitalize()})")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Macro F1")
    axes[1].legend()
    axes[1].grid(True, linestyle="--", alpha=0.5)
    
    curve_path = plots_dir / f"training_curves_{task}.png"
    plt.tight_layout()
    plt.savefig(curve_path, dpi=200)
    plt.close()
    print(f"\nSaved training curve plot: {curve_path}")
    
    # Plot B: Confusion Matrices
    for m in [test_metrics, test21_metrics]:
        cm = np.array(m["confusion_matrix"])
        cm_norm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        cm_norm = np.nan_to_num(cm_norm)
        
        plt.figure(figsize=(7, 6))
        sns.heatmap(
            cm_norm, annot=True, fmt=".2%", cmap="Blues",
            xticklabels=class_names, yticklabels=class_names
        )
        plt.title(f"Normalized Confusion Matrix: {m['name']} ({task.capitalize()})")
        plt.ylabel("True Class")
        plt.xlabel("Predicted Class")
        plt.tight_layout()
        cm_path = plots_dir / f"confusion_matrix_{m['name'].lower().replace('+', 'plus')}_{task}.png"
        plt.savefig(cm_path, dpi=200)
        plt.close()
        print(f"Saved confusion matrix plot: {cm_path}")
        
    # 12. Save Results JSON
    results = {
        "task": task,
        "input_features": input_dim,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": lr,
        "class_names": class_names,
        "kdd_test_plus": test_metrics,
        "kdd_test_21": test21_metrics
    }
    results_path = script_dir / f"results_{task}.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved results summary: {results_path}")
    
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train PyTorch MLP for NSL-KDD")
    parser.add_argument("--task", type=str, choices=["multiclass", "binary", "both"], default="both",
                        help="Classification task: multiclass, binary, or both (default: both)")
    parser.add_argument("--epochs", type=int, default=25, help="Number of epochs (default: 25)")
    parser.add_argument("--batch_size", type=int, default=256, help="Batch size (default: 256)")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate (default: 0.001)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()
    
    if args.task in ["multiclass", "both"]:
        run_experiment("multiclass", epochs=args.epochs, batch_size=args.batch_size, lr=args.lr, seed=args.seed)
    if args.task in ["binary", "both"]:
        run_experiment("binary", epochs=args.epochs, batch_size=args.batch_size, lr=args.lr, seed=args.seed)

