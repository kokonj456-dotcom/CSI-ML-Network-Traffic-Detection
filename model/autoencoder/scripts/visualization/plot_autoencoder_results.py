import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix

# ==========================================
# 1. กำหนดตำแหน่งไฟล์
# ==========================================

AUTOENCODER_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = AUTOENCODER_DIR.parents[1]
MODEL_DIR = AUTOENCODER_DIR
RESULTS_DIR = MODEL_DIR / "results"
CSV_DIR = RESULTS_DIR / "csv"
PNG_DIR = RESULTS_DIR / "png"

PNG_DIR.mkdir(parents=True, exist_ok=True)
CSV_DIR.mkdir(parents=True, exist_ok=True)

# ค้นหาไฟล์สรุปผลการประเมิน
details_candidates = [
    CSV_DIR / "unseen_attack_details.csv",
    CSV_DIR / "unseen_attack_details_kddtest.csv",
    MODEL_DIR / "unseen_attack_details.csv",
    MODEL_DIR / "unseen_attack_details_kddtest.csv",
]
summary_candidates = [
    CSV_DIR / "unseen_attack_results.csv",
    CSV_DIR / "unseen_attack_results_kddtest.csv",
    MODEL_DIR / "unseen_attack_results.csv",
    MODEL_DIR / "unseen_attack_results_kddtest.csv",
]

details_path = next((p for p in details_candidates if p.exists()), None)
summary_path = next((p for p in summary_candidates if p.exists()), None)

if not details_path or not summary_path:
    raise FileNotFoundError(
        "ไม่พบ CSV ผลประเมิน กรุณารัน evaluate_unseen.py ให้สำเร็จก่อน"
    )

details = pd.read_csv(details_path)
summary = pd.read_csv(summary_path)


# ==========================================
# 2. กราฟ Confusion Matrix
# ==========================================

y_true = details["is_attack"].astype(int)
y_pred = details["predicted_attack"].astype(int)

cm = confusion_matrix(
    y_true,
    y_pred,
    labels=[0, 1],
)

display = ConfusionMatrixDisplay(
    confusion_matrix=cm,
    display_labels=["Normal", "Attack"],
)

fig, ax = plt.subplots(figsize=(7, 6))
display.plot(
    ax=ax,
    values_format=",",
    colorbar=False,
)

ax.set_title("Autoencoder Confusion Matrix (KDDTest)")
ax.set_xlabel("Predicted Label")
ax.set_ylabel("Actual Label")

fig.tight_layout()
out_cm = PNG_DIR / "confusion_matrix.png"
fig.savefig(
    out_cm,
    dpi=300,
    bbox_inches="tight",
)
plt.close(fig)


# ==========================================
# 3. กราฟ Detection Rate แยกตาม Attack Label
# ==========================================

summary = summary.sort_values("detection_rate")

fig_height = max(8, len(summary) * 0.32)
fig, ax = plt.subplots(figsize=(11, fig_height))

bars = ax.barh(
    summary["label"].astype(str),
    summary["detection_rate"] * 100,
)

# แสดงค่าเปอร์เซ็นต์ที่ปลายแท่ง
for bar, value in zip(bars, summary["detection_rate"] * 100):
    ax.text(
        min(value + 1, 101),
        bar.get_y() + bar.get_height() / 2,
        f"{value:.1f}%",
        va="center",
        fontsize=8,
    )

ax.set_xlim(0, 115)
ax.set_xlabel("Detection Rate (%)")
ax.set_ylabel("Attack Label")
ax.set_title("Autoencoder Detection Rate by Attack Label")
ax.grid(axis="x", linestyle="--", alpha=0.3)

fig.tight_layout()
out_bar = PNG_DIR / "detection_rate_by_attack.png"
fig.savefig(
    out_bar,
    dpi=300,
    bbox_inches="tight",
)
plt.close(fig)


# ==========================================
# 4. สรุปไฟล์ที่สร้าง
# ==========================================

print("สร้างกราฟเรียบร้อยแล้ว")
print(f"Confusion Matrix: {out_cm}")
print(f"Detection Rate:   {out_bar}")
