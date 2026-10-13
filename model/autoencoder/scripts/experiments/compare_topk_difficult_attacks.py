from pathlib import Path
import pandas as pd

AUTOENCODER_DIR = Path(__file__).resolve().parents[2]
MODEL_DIR = AUTOENCODER_DIR
CSV_DIR = MODEL_DIR / "results" / "csv"

candidates = [
    CSV_DIR / "topk_scoring_by_attack.csv",
    MODEL_DIR / "topk_scoring_by_attack.csv",
]

csv_path = next((p for p in candidates if p.exists()), None)

if not csv_path:
    raise FileNotFoundError(
        "ไม่พบไฟล์ topk_scoring_by_attack.csv กรุณารัน evaluate_topk_scoring.py ก่อน"
    )

df = pd.read_csv(csv_path)

targets = ["snmpguess", "snmpgetattack", "mailbomb"]

selected = df[df["attack_label"].str.lower().isin(targets)].copy()

if selected.empty:
    raise ValueError(
        "No matching attack labels found. Check the labels in topk_scoring_by_attack.csv."
    )

selected["recall_percent"] = selected["recall"] * 100

print("=== Top-k results for difficult attack families ===")
print(
    selected[
        [
            "attack_label",
            "method",
            "total",
            "detected",
            "missed",
            "recall_percent",
        ]
    ]
    .sort_values(["attack_label", "method"])
    .round(2)
    .to_string(index=False)
)

print("\n=== Recall comparison by attack ===")
pivot = selected.pivot(
    index="attack_label",
    columns="method",
    values="recall_percent",
)
print(pivot.round(2).to_string())
