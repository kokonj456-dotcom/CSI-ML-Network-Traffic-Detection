# Isolation Forest + alert clustering

This experiment uses Isolation Forest as an **unsupervised anomaly scorer** and a separate K-Means model to group records that were flagged for review. Isolation Forest itself does not create clusters.

## Run from the repository root

1. Download the dataset if it is not already present:

   ```powershell
   python dataset/download_nsl_dataset.py
   ```

2. Run these notebooks in order:

   - `data-pipeline/nsl_cleansing.ipynb`
   - `data-pipeline/nsl_feature_engineering.ipynb`

3. Install this experiment's dependencies and run it:

   ```powershell
   python -m pip install -r model/isolation-forest/requirements.txt
   python model/isolation-forest/train.py --alert-rate 0.05 --clusters 5
   ```

The scripts resolve data paths from their own locations. To start one while the current directory is elsewhere, invoke the Python file by its absolute path.

## Code layout

- `train.py`: command-line entry point and options.
- `src/data.py`: dataset paths, loading, input/schema checks, and baseline feature selection.
- `src/preprocessing.py`: transformations used only to prepare flagged records for clustering.
- `src/training.py`: Isolation Forest/K-Means fitting, scoring, and experiment orchestration.
- `src/evaluation.py`: post-hoc benchmark metrics; labels are read only after model scoring.
- `src/reporting.py`: CSV/JSON artifact creation and cluster summaries.

Run the experiment through `train.py`; implementation modules are grouped under `src/`.

## What the experiment does

- Fits Isolation Forest on **KDDTrain features only**. `label`, `attack_family`, and `is_attack` are never passed into either model's `fit` method.
- Uses only original numeric features and the One-Hot columns from the training vocabulary. Engineered alternatives are left out of this first baseline so duplicate or questionable derived features do not silently get extra influence.
- Sets the initial alert threshold at the selected quantile of KDDTrain anomaly scores. `--alert-rate 0.05` means “review approximately the most unusual 5% of training records”; it does **not** mean the attack rate is 5% or that the model has 5% error.
- For clustering only, applies `log1p` to selected skewed non-negative counts/bytes, robust-scales numeric columns, and balances the numeric block with the three categorical one-hot groups. Fits K-Means on flagged KDDTrain records and assigns those learned groups to flagged KDDTest and KDDTest-21 records. `cluster_id = -1` means “not flagged for review,” not a K-Means noise cluster.
- Uses the saved targets only after scoring to report benchmark metrics and inspect cluster composition. These labels do not change anomaly scores, thresholds, or cluster assignments.

## Output

Generated files are written to the ignored local directory:

```text
data-pipeline/output/NSL-KDD/isolation_forest/
```

- `KDDTrain_anomaly_results.csv`, `KDDTest_anomaly_results.csv`, `KDDTest-21_anomaly_results.csv`: row index, anomaly score, flag, cluster, and reference targets for post-hoc inspection.
- `KDDTest_alerts.csv`, `KDDTest-21_alerts.csv`: flagged records and their feature values, sorted from most suspicious to least suspicious.
- `evaluation_metrics.csv`: ranking metrics and threshold-based precision/recall/F1/false-positive rate; also reports recall on attack labels absent from KDDTrain.
- `training_alert_cluster_profiles.csv`: training alert cluster sizes and label/service summaries for interpretation only.
- `run_config.json`: feature set, threshold, seed, cluster count, and output location.

The default threshold is only a starting operating point. Choose it for the number of alerts the reviewer can handle, and report the resulting false-positive rate and recall. Do not tune it against KDDTest and then report that same Test result as an untouched final evaluation.

This is a benchmark prototype, not proof that every flagged record is malicious. An unusual but benign connection can also be flagged. Cluster IDs are arbitrary group numbers and should be interpreted from their feature profiles, not as attack-family names.
