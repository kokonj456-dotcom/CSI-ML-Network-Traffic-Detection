# Pipeline file guide

Current execution and output contract: [README.md](README.md).

| Location | Responsibility |
|---|---|
| `build_quad_dataset.py` | Isolated full rebuild, UTF-8 execution, source checks, audit and reversible publishing |
| `pipeline_runtime.py` | Strict table/manifest checks, per-source label maps, grouped splitting, shared encoding, SMOTENC and complete output audit |
| `audit_all_pipelines.py` | CLI validation with nonzero failure status |
| `sub-dataset/<name>/cleansing.ipynb` | Source-specific cleansing and raw manifests |
| `sub-dataset/<name>/harmonization.ipynb` | Source-specific field mapping, measured availability, aligned tables and dependency stamps |
| `sub-dataset/CIC-IDS2017/download.py`, `sub-dataset/BoT-IoT/download.py` | Explicit online/demo preparation with source provenance; no fallback |
| `CENTRAL/build_dataset.ipynb` | Notebook entry point for shared central builder |
| `CENTRAL/feature_engineering.ipynb` | Notebook entry point for shared train-fitted encoding |
| `CENTRAL/borderline_smote.ipynb` | Legacy filename; notebook entry point for SMOTENC |
| `tests/test_pipeline_runtime.py` | Regression cases for mapping, invalid inputs, stale data, encoding, resampling and source failures |

`common/` paths and old fixed row counts in historical analysis documents are obsolete. Current reports are created under `CENTRAL/output/reports` and refer to one recorded run. Historical model dashboards are not automatically refreshed by this data pipeline.