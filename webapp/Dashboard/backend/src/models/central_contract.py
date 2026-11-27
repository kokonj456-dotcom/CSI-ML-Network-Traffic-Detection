"""CENTRAL feature names, preprocessing and model input contract."""

import hashlib

import numpy as np
import pandas as pd
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC = ["duration", "bytes_forward", "bytes_backward"]
CATEGORIES = {
    "protocol": ["tcp", "udp", "icmp", "other"],
    "service_group": ["dns", "ftp", "http", "https_ssl", "smtp", "ssh", "other"],
    "conn_state_group": ["established", "no-reply", "reset", "other"],
}
CORE = NUMERIC + list(CATEGORIES)
PREFIXES = ["proto", "service", "state"]
NAMES = [
    "log_duration",
    "log_bytes_forward",
    "log_bytes_backward",
    "signed_log_bytes_ratio",
] + [
    f"{prefix}_{value}"
    for prefix, values in zip(PREFIXES, CATEGORIES.values())
    for value in values
]
CLASS_NAMES = [
    "Benign / Normal",
    "Denial of Service (DoS)",
    "Reconnaissance & Probing",
    "Exploits & PrivEsc",
    "Credential Abuse (R2L)",
    "Malware, C2 & Botnet",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def derived(f):
    x = np.log1p(f[NUMERIC].to_numpy(float))
    return np.column_stack([x, x[:, 1] - x[:, 2]])


def fit_preprocessor(f):
    enc = OneHotEncoder(
        categories=list(CATEGORIES.values()),
        sparse_output=False,
        handle_unknown="error",
    )
    enc.fit(f[list(CATEGORIES)])
    return {
        "scaler": StandardScaler().fit(derived(f)),
        "encoder": enc,
        "model_feature_names": NAMES,
        "fit_record_ids_sha256": hashlib.sha256(
            "\n".join(f.record_id.astype(str)).encode()
        ).hexdigest(),
        "fit_split": "train",
        "schema_version": 5,
    }


def transform_features(f, preprocessor):
    # Validation is shared with resampling; no silent clipping or imputation.
    for c in NUMERIC:
        require(np.isfinite(f[c]).all() and f[c].ge(0).all(), f"Invalid {c}")
    for c, values in CATEGORIES.items():
        require(f[c].isin(values).all(), f"Invalid {c}")
    x = np.column_stack(
        [
            preprocessor["scaler"].transform(derived(f)),
            preprocessor["encoder"].transform(f[list(CATEGORIES)]),
        ]
    )
    require(np.isfinite(x).all(), "Encoded features are not finite")
    result = pd.DataFrame(x, columns=NAMES)
    result.insert(0, "record_id", f.record_id.to_numpy())
    return result
