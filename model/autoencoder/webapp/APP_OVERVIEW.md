# App overview

This is a local-only web application for testing the existing Autoencoder pipeline.

- UI: HTML/CSS/JavaScript served by FastAPI (no separate Node install required)
- API: FastAPI
- ML: existing PyTorch Autoencoder and NSL-KDD engineered CSVs
- History: SQLite at `results/experiments.sqlite3`
- Per-run artifacts: `results/web_runs/<experiment-id>/`
- Test dataset: KDDTest only in this first version
- Models supported: Autoencoder only

For launch steps, see `README.md`.
