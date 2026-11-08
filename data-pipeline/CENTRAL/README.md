# CENTRAL notebooks

Use `python data-pipeline/build_quad_dataset.py` from the project root for the full validated rebuild. Existing legacy/demo inputs require explicit `--allow-unverified-data`; optional resampling is `--resampling smotenc`.

The notebooks call shared implementation in `../pipeline_runtime.py` to prevent schema/scaling/mapping drift:

1. `build_dataset.ipynb`: validate harmonized dependency stamps, map labels strictly, group validation inputs, preserve supplied tests, write splits and overlap reports.
2. `feature_engineering.ipynb`: fit the single 19-column preprocessor on train and reuse it across all splits.
3. `borderline_smote.ipynb`: legacy filename for categorical-aware SMOTENC; run after feature engineering and set the tagged `SMOTE_SPLIT` parameter to train or train_full.

Dataset harmonization notebooks can run separately after cleansing. Any code/config/raw change invalidates their dependency stamps and requires rebuilding. The master runner always rebuilds all stages.

See `../README.md` for source verification, commands, output locations, weighting, schema compatibility and validation limits. Older analysis notebooks are exploratory snapshots and are not part of the validated production path; rerun/adapt them against the selected run before citing their statistics.