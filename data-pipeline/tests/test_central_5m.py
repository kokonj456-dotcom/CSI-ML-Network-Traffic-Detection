"""Unit tests for CENTRAL-5M pipeline invariants."""
import json
import unittest
from pathlib import Path

import pyarrow.parquet as pq

PIPELINE_DIR = Path(__file__).resolve().parents[1]
CENTRAL_5M_DIR = PIPELINE_DIR / "CENTRAL-5M"


class Central5MTests(unittest.TestCase):
    def test_directory_and_contract_structure(self):
        self.assertTrue(CENTRAL_5M_DIR.is_dir(), "CENTRAL-5M directory must exist")
        self.assertTrue((CENTRAL_5M_DIR / "feature_contract.json").is_file())
        self.assertTrue((CENTRAL_5M_DIR / "dataset_registry.json").is_file())
        self.assertTrue((CENTRAL_5M_DIR / "README.md").is_file())
        self.assertTrue((CENTRAL_5M_DIR / "build_dataset_5m.ipynb").is_file())

    def test_audit_invariants(self):
        audit_path = CENTRAL_5M_DIR / "output/reports/audit.json"
        self.assertTrue(audit_path.is_file(), "audit.json must exist")
        with open(audit_path) as f:
            audit = json.load(f)

        self.assertEqual(audit.get("status"), "passed")
        self.assertEqual(audit.get("format"), "Parquet-First")
        self.assertGreaterEqual(audit.get("total_records", 0), 5_000_000)

        invariants = audit.get("invariants", {})
        for inv_name, passed in invariants.items():
            self.assertTrue(passed, f"Invariant {inv_name} must be True")

    def test_parquet_file_integrity(self):
        train_feat_path = CENTRAL_5M_DIR / "output/splits/train/features.parquet"
        self.assertTrue(train_feat_path.is_file())
        schema = pq.read_schema(train_feat_path)
        # 19 features + record_id = 20 columns
        self.assertEqual(len(schema.names), 20)
        self.assertIn("record_id", schema.names)
        self.assertIn("log_duration", schema.names)
        self.assertIn("proto_tcp", schema.names)
        self.assertIn("service_http", schema.names)
        self.assertIn("state_established", schema.names)


if __name__ == "__main__":
    unittest.main()
