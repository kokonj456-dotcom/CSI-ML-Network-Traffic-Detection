"""CLI entry point for the Isolation Forest experiment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Keep this long-standing entry point while implementation modules live in src/.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from training import run_training


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fit Isolation Forest without labels, flag records by a training-score "
            "quantile, then cluster flagged training records."
        )
    )
    parser.add_argument(
        "--alert-rate",
        type=float,
        default=0.05,
        help="Share of training records used to set the initial alert threshold (default: 0.05).",
    )
    parser.add_argument(
        "--clusters",
        type=int,
        default=5,
        help="Requested number of K-Means groups among flagged training records (default: 5).",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42).")
    parser.add_argument(
        "--estimators",
        type=int,
        default=300,
        help="Number of Isolation Forest trees (default: 300).",
    )
    return parser.parse_args()


def main() -> None:
    run_training(parse_args())


if __name__ == "__main__":
    main()
