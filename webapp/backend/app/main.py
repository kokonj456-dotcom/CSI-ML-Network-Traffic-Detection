"""
FastAPI Server Entrypoint for Multi-Dataset NIDS Dashboard
"""

from __future__ import annotations

# Import torch before third-party C/C++ libraries (such as xgboost / scikit-learn)
# to avoid OpenMP runtime TLS collision on macOS
import torch

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from pydantic import BaseModel
from app.data_loader import store
from app.training_service import (
    get_available_training_config,
    train_model_pipeline,
    get_training_history,
    start_training_job,
    get_job_status,
)

class TrainRequest(BaseModel):
    family: str
    dataset: str
    target_type: str = "binary"
    hyperparameters: dict = {}

app = FastAPI(
    title="NSL-KDD & Multi-Dataset Pipeline Dashboard API",
    description="Backend API for exploratory data analysis, data quality checks, harmonization contract, and models evaluation.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "NIDS Pipeline & Benchmark API"}

@app.get("/api/datasets")
def list_datasets():
    return store.get_dataset_metadata()

@app.get("/api/eda")
def get_eda(
    dataset: str = Query("common", description="Dataset identifier: common, nsl-kdd, or unsw-nb15"),
    split: str = Query("all", description="Split partition filter")
):
    return store.get_eda_summary(dataset_id=dataset, split=split)

@app.get("/api/cleansing")
def get_cleansing(
    dataset: str = Query("common", description="Dataset identifier: common, nsl-kdd, or unsw-nb15")
):
    return store.get_cleansing_report(dataset_id=dataset)

@app.get("/api/features")
def get_features():
    return store.get_feature_contract()

@app.get("/api/models")
def get_models():
    runs = store.get_all_model_runs()
    families = sorted(list(set(r["family"] for r in runs)))
    return {
        "total_runs": len(runs),
        "families": families,
        "runs": runs
    }

@app.delete("/api/models")
def delete_model(model_id: str = Query(..., description="Compound model run identifier or directory name")):
    success = store.delete_model_run(model_id=model_id)
    return {"success": success, "model_id": model_id}

@app.get("/api/training/config")
def training_config():
    return get_available_training_config()

@app.get("/api/training/history")
def training_history():
    return {"history": get_training_history()}

@app.post("/api/training/start")
def start_training_endpoint(req: TrainRequest):
    job_id = start_training_job(
        family=req.family,
        dataset_id=req.dataset,
        params=req.hyperparameters,
        target_type=req.target_type,
        on_finish_cache_clear=lambda: store._cache.clear()
    )
    return {"job_id": job_id, "status": "started"}

@app.get("/api/training/status")
def job_status_endpoint(job_id: str = Query(..., description="Job identifier")):
    return get_job_status(job_id)

@app.post("/api/training/train")
def train_model_endpoint(req: TrainRequest):
    result = train_model_pipeline(
        family=req.family,
        dataset_id=req.dataset,
        params=req.hyperparameters
    )
    store._cache.clear()
    return result



