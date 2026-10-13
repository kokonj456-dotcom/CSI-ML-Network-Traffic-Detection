"""Prepare and verify the official UNSW-NB15 train/test CSV files.

The official UNSW download page currently points to a SharePoint location that
may require a university login. This script does not try to bypass that login:
download the two CSVs through the official page, save them in ``raw/``, then
run this script again to verify them. Direct download URLs can also be supplied
with the command-line options below.
"""

from __future__ import annotations

import argparse
import csv
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


OFFICIAL_PAGE = "https://research.unsw.edu.au/projects/unsw-nb15-dataset"
RAW_DIR = Path(__file__).resolve().parent / "raw"

DATA_FILES = {
    "training": {
        "filename": "UNSW_NB15_training-set.csv",
        "expected_rows": 175_341,
    },
    "testing": {
        "filename": "UNSW_NB15_testing-set.csv",
        "expected_rows": 82_332,
    },
}

REQUIRED_COLUMNS = {
    "id",
    "dur",
    "proto",
    "service",
    "state",
    "sbytes",
    "dbytes",
    "attack_cat",
    "label",
}


def check_csv(csv_path: Path, expected_rows: int) -> int:
    """Check that a file is a complete UNSW train/test CSV and return its rows."""
    if not csv_path.is_file() or csv_path.stat().st_size == 0:
        raise ValueError(f"ไฟล์ไม่มีอยู่หรือว่างเปล่า: {csv_path}")

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file)
            header = next(reader, None)
            if not header:
                raise ValueError("ไม่พบ header ในไฟล์ CSV")

            header = [column.strip() for column in header]
            missing_columns = REQUIRED_COLUMNS.difference(header)
            if missing_columns:
                raise ValueError(
                    "header ไม่ตรงกับ UNSW-NB15; ขาดคอลัมน์: "
                    + ", ".join(sorted(missing_columns))
                )

            row_count = 0
            for row_count, row in enumerate(reader, start=1):
                if len(row) != len(header):
                    raise ValueError(
                        f"แถวข้อมูลลำดับ {row_count} มี {len(row)} ช่อง "
                        f"แต่ header มี {len(header)} คอลัมน์"
                    )
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValueError(f"อ่านไฟล์ CSV ไม่สำเร็จ: {error}") from error

    if row_count != expected_rows:
        raise ValueError(
            f"จำนวนแถวไม่ตรงกับชุด official: พบ {row_count:,} แถว "
            f"แต่ควรเป็น {expected_rows:,} แถว"
        )

    return row_count


def download_csv(name: str, url: str, destination: Path) -> None:
    """Download to a temporary file, validate it, then safely move it into place."""
    temporary_path = destination.with_name(destination.name + ".part")
    expected_rows = DATA_FILES[name]["expected_rows"]
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CSI-ML-Final-UNSW-NB15-downloader/1.0"},
    )

    try:
        print(f"กำลังดาวน์โหลด {destination.name} ...")
        with urllib.request.urlopen(request, timeout=120) as response:
            with temporary_path.open("wb") as output_file:
                while chunk := response.read(1024 * 1024):
                    output_file.write(chunk)

        check_csv(temporary_path, expected_rows)
        temporary_path.replace(destination)
        print(f"บันทึกและตรวจสอบแล้ว: {destination}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise RuntimeError(
            f"ดาวน์โหลด/ตรวจสอบ {destination.name} ไม่สำเร็จ: {error}\n"
            "ถ้าลิงก์พาไปหน้า login ให้ดาวน์โหลดผ่านบัญชีที่ได้รับอนุญาต "
            "แล้ววาง CSV ในโฟลเดอร์ raw/"
        ) from error
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="เตรียมและตรวจสอบไฟล์ official train/test ของ UNSW-NB15"
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=RAW_DIR,
        help=f"โฟลเดอร์เก็บ CSV (ค่าเริ่มต้น: {RAW_DIR})",
    )
    parser.add_argument(
        "--training-url",
        help="direct URL สำหรับไฟล์ training (ถ้า URL ต้อง login ให้ดาวน์โหลดเอง)",
    )
    parser.add_argument(
        "--testing-url",
        help="direct URL สำหรับไฟล์ testing (ถ้า URL ต้อง login ให้ดาวน์โหลดเอง)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="ดาวน์โหลดทับไฟล์เดิม (ต้องระบุ URL ที่ต้องการดาวน์โหลดด้วย)",
    )
    parser.add_argument(
        "--open-page",
        action="store_true",
        help="เปิดหน้าโครงการ UNSW ทางการเมื่อไฟล์ยังไม่ครบ",
    )
    args = parser.parse_args()

    if args.force and not (args.training_url or args.testing_url):
        parser.error("--force ต้องใช้ร่วมกับ --training-url หรือ --testing-url")

    raw_dir = args.raw_dir.expanduser().resolve()
    raw_dir.mkdir(parents=True, exist_ok=True)
    supplied_urls = {
        "training": args.training_url,
        "testing": args.testing_url,
    }

    for name, details in DATA_FILES.items():
        destination = raw_dir / details["filename"]
        url = supplied_urls[name]

        if destination.is_file() and not args.force:
            print(f"พบไฟล์แล้ว ไม่ดาวน์โหลดซ้ำ: {destination.name}")
            continue

        if url:
            try:
                download_csv(name, url, destination)
            except RuntimeError as error:
                print(error, file=sys.stderr)
                return 1

    missing_files = [
        details["filename"]
        for details in DATA_FILES.values()
        if not (raw_dir / details["filename"]).is_file()
    ]
    if missing_files:
        print("ยังขาดไฟล์: " + ", ".join(missing_files), file=sys.stderr)
        print(f"1. เปิดหน้าดาวน์โหลด official: {OFFICIAL_PAGE}", file=sys.stderr)
        print("2. ดาวน์โหลด train/test CSV และวางไว้ที่:", raw_dir, file=sys.stderr)
        print("3. รันคำสั่งนี้อีกครั้งเพื่อตรวจชื่อไฟล์/schema/จำนวนแถว", file=sys.stderr)
        if args.open_page:
            webbrowser.open(OFFICIAL_PAGE)
        return 1

    print("\nผลตรวจสอบไฟล์:")
    try:
        for details in DATA_FILES.values():
            csv_path = raw_dir / details["filename"]
            rows = check_csv(csv_path, details["expected_rows"])
            print(f"- {csv_path.name}: {rows:,} แถว, {csv_path.stat().st_size:,} bytes")
    except ValueError as error:
        print(f"ตรวจสอบไม่ผ่าน: {error}", file=sys.stderr)
        return 1

    print(f"\nพร้อมใช้แล้ว: {raw_dir}")
    print("ขั้นถัดไป: รัน eda.ipynb แล้ว cleansing.ipynb")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
