"""Preprocessing used only by the alert-record clustering stage."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler


class MixedFeatureClusterer:
    """Compress skewed counts, scale numeric fields, and balance category groups."""

    LOG_COLUMNS = {
        "duration",
        "src_bytes",
        "dst_bytes",
        "count",
        "srv_count",
        "dst_host_count",
        "dst_host_srv_count",
        "hot",
        "num_failed_logins",
        "num_compromised",
        "num_root",
        "num_file_creations",
        "num_access_files",
    }

    def __init__(self, feature_schema: pd.DataFrame) -> None:
        self.numeric_columns = feature_schema.loc[
            feature_schema["kind"] == "original_numeric", "feature"
        ].astype(str).tolist()
        self.one_hot_columns = feature_schema.loc[
            feature_schema["kind"] == "one_hot", "feature"
        ].astype(str).tolist()
        self.category_group_count = len(
            {
                column.split("=", maxsplit=1)[0]
                for column in self.one_hot_columns
                if "=" in column
            }
        )
        self.scaler = RobustScaler(quantile_range=(10.0, 90.0))
        self.numeric_weight = math.sqrt(
            max(self.category_group_count, 1) / max(len(self.numeric_columns), 1)
        )

    def _numeric_values(self, frame: pd.DataFrame) -> pd.DataFrame:
        values = frame[self.numeric_columns].copy()
        for column in self.LOG_COLUMNS.intersection(self.numeric_columns):
            values[column] = np.log1p(values[column].clip(lower=0))
        return values

    def fit_transform(self, frame: pd.DataFrame) -> np.ndarray:
        numeric = self.scaler.fit_transform(self._numeric_values(frame))
        categories = frame[self.one_hot_columns].to_numpy(dtype=np.float32, copy=True)
        return np.column_stack((numeric * self.numeric_weight, categories))

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        numeric = self.scaler.transform(self._numeric_values(frame))
        categories = frame[self.one_hot_columns].to_numpy(dtype=np.float32, copy=True)
        return np.column_stack((numeric * self.numeric_weight, categories))
