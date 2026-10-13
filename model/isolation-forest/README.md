# Isolation Forest + alert clustering

This experiment uses Isolation Forest as an **unsupervised anomaly scorer** and a separate K-Means model to group records that were flagged for review. Isolation Forest itself does not create clusters.

## Run from the repository root

1. Download the dataset if it is not already present:

   ```powershell
   python data-pipeline/NSL-KDD/download.py
   ```

2. Run these notebooks in order:

   - `data-pipeline/NSL-KDD/cleansing.ipynb`
   - `data-pipeline/NSL-KDD/feature_engineering.ipynb`

3. Install this experiment's dependencies and run it:

   ```powershell
   python -m pip install -r model/isolation-forest/requirements.txt
   python model/isolation-forest/train.py --alert-rate 0.05 --clusters 5
   ```

   For a training-only walkthrough in one file, run `python model/isolation-forest/train_single.py` instead. It fits Isolation Forest on KDDTrain features only; it does not evaluate test data or create clusters. Its model and training configuration are saved under `data-pipeline/NSL-KDD/output/model_runs/isolation_forest_single/`.

The scripts resolve data paths from their own locations. To start one while the current directory is elsewhere, invoke the Python file by its absolute path.

## Run the common-dataset comparison

After the common pipeline has created its split and `joint_v1` feature files, run:

```powershell
python model/isolation-forest/train_common.py
```

This separate experiment compares the previous 10-feature `joint_v0` profile with the 19-feature `joint_v1` profile, then evaluates `joint_v1` in both NSL-KDD → UNSW-NB15 and UNSW-NB15 → NSL-KDD directions. It uses 300 trees, seed 42, and a threshold set from the 95th percentile of training anomaly scores by default. Labels are read only for post-score evaluation; they are not used to fit Isolation Forest or choose the threshold. Results are split out by dataset and saved with the combined `joint_v1` model under `model/isolation-forest/backup/`.

Optional arguments are `--estimators`, `--seed`, and `--alert-rate` (for example, `--alert-rate 0.05`). This does not change the original NSL-KDD trainer above.

## Code layout

- `train.py`: command-line entry point and options.
- `train_single.py`: beginner-friendly, single-file training script; reads only the feature table and never loads targets.
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

Generated reports are written to the ignored local directory:

```text
data-pipeline/NSL-KDD/output/model_runs/isolation_forest/
```

- `KDDTrain_anomaly_results.csv`, `KDDTest_anomaly_results.csv`, `KDDTest-21_anomaly_results.csv`: row index, anomaly score, flag, cluster, and reference targets for post-hoc inspection.
- `KDDTest_alerts.csv`, `KDDTest-21_alerts.csv`: flagged records and their feature values, sorted from most suspicious to least suspicious.
- `evaluation_metrics.csv`: ranking metrics and threshold-based precision/recall/F1/false-positive rate; also reports recall on attack labels absent from KDDTrain.
- `training_alert_cluster_profiles.csv`: training alert cluster sizes and label/service summaries for interpretation only.
- `run_config.json`: feature set, threshold, seed, cluster count, and output location.

Every successful run also creates a timestamp-matched pair under
`model/isolation-forest/backup/`:

- `isolation-forest-iso-<เวลา>.joblib`: a reusable bundle containing the fitted Isolation Forest,
  alert threshold, portable fitted clustering-preprocessing state, K-Means model, feature names,
  and run settings.
- `isolation-forest-iso-<เวลา>-result.json`: model parameters and evaluation results for both
  `KDDTest` and `KDDTest-21`. Test labels are used only after scoring; they are not used to fit
  the Isolation Forest or choose the threshold.

For example, one run may produce `isolation-forest-iso-20261012-143520-123456.joblib` and its
matching `isolation-forest-iso-20261012-143520-123456-result.json`.

The timestamp includes date, time, and microseconds so repeated runs do not overwrite earlier
backups. The backup folder is ignored by Git because it contains generated model artifacts and
run-specific results.

The default threshold is only a starting operating point. Choose it for the number of alerts the reviewer can handle, and report the resulting false-positive rate and recall. Do not tune it against KDDTest and then report that same Test result as an untouched final evaluation.

This is a benchmark prototype, not proof that every flagged record is malicious. An unusual but benign connection can also be flagged. Cluster IDs are arbitrary group numbers and should be interpreted from their feature profiles, not as attack-family names.
