import argparse
from pathlib import Path

from urllib.request import urlopen

BASE_URL = "https://raw.githubusercontent.com/defcom17/NSL_KDD/master"

FILES = [
    "KDDTrain+.txt",
    "KDDTest+.txt",
    "KDDTrain+_20Percent.txt",
    "KDDTest-21.txt",
]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOWNLOAD_DIR = PROJECT_ROOT / "dataset" / "rawdata" / "NSL-KDD"


def download_file(filename: str, download_dir: Path, force: bool = False) -> Path:
    url = f"{BASE_URL}/{filename}"
    save_path = download_dir / filename
    temporary_path = save_path.with_name(save_path.name + ".part")

    if save_path.is_file() and save_path.stat().st_size > 0 and not force:
        print(f"Already exists, skipping: {save_path}")
        return save_path

    print(f"Downloading {filename}...")
    try:
        bytes_written = 0
        with urlopen(url, timeout=120) as response, temporary_path.open("wb") as file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                file.write(chunk)
                bytes_written += len(chunk)

        if bytes_written == 0:
            raise IOError(f"Downloaded file is empty: {filename}")

        temporary_path.replace(save_path)
        print(f"Saved: {save_path} ({bytes_written:,} bytes)")
        return save_path
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download the NSL-KDD source files into the project dataset folder."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DOWNLOAD_DIR,
        help=f"Download location (default: {DEFAULT_DOWNLOAD_DIR})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Download again even when a non-empty file already exists.",
    )
    args = parser.parse_args()

    download_dir = args.output_dir.expanduser().resolve()
    download_dir.mkdir(parents=True, exist_ok=True)

    for filename in FILES:
        download_file(filename, download_dir, force=args.force)

    missing_files = [
        filename
        for filename in FILES
        if not (download_dir / filename).is_file()
        or (download_dir / filename).stat().st_size == 0
    ]
    if missing_files:
        raise RuntimeError(f"Download verification failed: {missing_files}")

    print(f"\nNSL-KDD dataset is ready at: {download_dir}")


if __name__ == "__main__":
    main()
