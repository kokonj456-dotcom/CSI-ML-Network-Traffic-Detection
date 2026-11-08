# Data pipeline — validated rebuilds

The current entry point rebuilds all four local datasets from raw, validates every stage, builds CENTRAL, fits one shared preprocessor on train, and audits before publishing. Implementation shared by CENTRAL notebooks is in `pipeline_runtime.py`; dataset-specific adapters remain in their notebooks.

```powershell
# Documented online source data; stops if CIC/BoT provenance is missing or measured attributes are unavailable
python data-pipeline/build_quad_dataset.py

# Existing legacy/demo inputs: explicit diagnostic run, not official benchmark certification
python data-pipeline/build_quad_dataset.py --allow-unverified-data

# Optional mixed numerical/categorical oversampling; default is an unresampled baseline
python data-pipeline/build_quad_dataset.py --allow-unverified-data --resampling smotenc

# Inspect a complete run without publishing
python data-pipeline/build_quad_dataset.py --allow-unverified-data --resampling smotenc --no-publish

# Validate current published outputs; include the resampled datasets when present
python data-pipeline/audit_all_pipelines.py --resampled
python -m unittest discover -s data-pipeline/tests -v
```

## Inputs and source provenance

Prepare local raw files under `sub-dataset/<dataset>/raw`. The main runner does not download or substitute inputs implicitly. CIC/BoT `download.py --source online` fails on download/schema errors. `--source emulate` is an explicit demo option. New preparations record URLs, mode, hashes and sampling policy in `raw/source_provenance.json`. Existing files without that record remain unverified; do not label them online simply because their names match a benchmark.

The CIC online adapter requires a measured `Protocol` field, converts duration from microseconds to seconds, and leaves connection state unavailable if the source does not supply it. The BoT adapter retains destination port when supplied; it never fabricates directional packet counts from a total. Harmonization marks missing service/state as unavailable in metadata. Such data may run only in diagnostic mode with the affected categorical value represented as `other`; this does not establish equivalent measured features across domains.

Locally sampled CIC/BoT splits are not official predefined train/test releases. NSL/UNSW supplied official train/test files retain their split identities. Data source documentation and hashes establish traceability; mirror names alone do not certify authenticity.

## Outputs and reuse

Each dataset writes `output/cleansing` and `output/harmonized`, including raw SHA-256 manifests and a dependency stamp covering source code, registry, contract and table hashes. CENTRAL rejects missing/stale stamps rather than trusting the existence of `features.csv`.

CENTRAL writes separate `features.csv`, `labels.csv`, `metadata.csv`, joined by unique `record_id`. IDs, target labels, source names, availability masks and weights are never model inputs.

- `output/splits/{train,validation,train_full,test}`: harmonized tables. `train_full` is the union of train and validation, not an independent split.
- `output/feature_engineering/{split}`: the same 19 encoded columns for every split.
- `output/feature_engineering/preprocessor.joblib`: one scaler/encoder fitted on train only, reused for validation, test and resampled data.
- Optional `output/splits/{train_smote,train_full_smote}`: SMOTENC outputs, encoded features and a separate `smote_report.json` per split. The old notebook filename `borderline_smote.ipynb` is retained for compatibility, but the algorithm is SMOTENC.
- `output/reports/label_mapping.csv`, `source_splits.csv`, `overlap.json`, `audit.json`: mapping, source composition, overlap and strict validation results.
- `output/build_manifest.json`, `data_sources.json`, `RUN_PROVENANCE.json`: reproducible run scope and dependency evidence.

Old `output/smote` aliases are no longer emitted. Use split-specific paths. New schema version 5 is incompatible with old unscaled/renamed 19-column model artifacts; retrain models with the saved current preprocessor.

## Label and split policy

Unknown source labels stop the build. Mappings are explicit per dataset; source binary truth must agree with the mapped normal/attack result. Six classes are a project taxonomy. MITRE fields annotate groups and do not prove an individual attack technique occurred.

Validation is assigned to entire groups of identical six shared model inputs using seed 42, without reading labels. Validation row counts may differ from exactly 20%. Test rows retain their supplied source split. `overlap.json` reports repeated vectors and conflicting labels rather than silently deleting them. Identical features do not necessarily mean the same capture event. Report test overlap and sensitivity metrics, metrics per source/class, and investigate raw session/time identifiers before claiming independence or performance on a new domain.

## Preprocessing, resampling and weights

Four numerical columns are log duration, log forward bytes, log backward bytes and their signed difference. StandardScaler is fitted on train. Fixed protocol/service/state categories produce 15 one-hot columns. Both baseline and synthetic records reuse this representation and column order (`proto_*`, `service_*`, `state_*`). Invalid/missing numerical inputs fail instead of being silently filled or clipped.

SMOTENC uses three standardized log numeric inputs plus the original categorical fields for its neighborhoods. It interpolates only numeric attributes and recomputes the redundant ratio after inverse transformation. Synthetic IDs include source split, class and seed. Labels and synthetic markers are audited, and validation/test are never resampled. For cross-validation, fit preprocessing and resampling inside each training fold.

Baseline source weights have equal total contribution per source and mean row weight 1 within each split. Resampled outputs deliberately use uniform weight 1 for every row; no extra class/source weighting is implied. Any additional weighting should be a separately evaluated experiment.

## Failure and publishing behavior

A new run is built under `.pipeline-runs/<run-id>/work`; its UTF-8 log is alongside `work`. Every stage runs afresh. Published outputs are moved into place only after the complete audit passes and original code/raw fingerprints still match. Previous output directories are retained under `.pipeline-archives/<run-id>`; unrelated model-run folders are retained. A failed run leaves published data unchanged. Publishing has rollback on Python exceptions; it is a sequence of directory moves, not a filesystem transaction against power loss.

Audit failures exit nonzero. Diagnostic success is explicitly marked diagnostic, with source/availability and official-test overlap warnings. Passing structural validation does not certify benchmark authenticity or model quality.