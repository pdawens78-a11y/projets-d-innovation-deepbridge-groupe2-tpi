"""
extract_cab_files.py
====================
Extract all .cab files from a scan folder into a scan_extracted folder,
with one subfolder per CAB to avoid filename collisions.

For each CAB, write one row in extraction_report.csv with:
- source CAB filename
- extracted file count
- extracted .dcm count
- success or error status
- extraction duration

The script prints progress for each CAB and a global summary at the end.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


REPORT_FIELDS = [
    "timestamp",
    "source_cab",
    "source_path",
    "output_subdir",
    "extracted_files",
    "extracted_dcm",
    "status",
    "error",
    "duration_seconds",
]


@dataclass
class ExtractionRow:
    timestamp: str
    source_cab: str
    source_path: str
    output_subdir: str
    extracted_files: int
    extracted_dcm: int
    status: str
    error: str
    duration_seconds: float


def find_cabs(scan_dir: Path) -> list[Path]:
    return sorted(p for p in scan_dir.rglob("*.cab") if p.is_file())


def count_extracted_files(folder: Path) -> tuple[int, int]:
    files = [p for p in folder.rglob("*") if p.is_file()]
    total = len(files)
    dcm = sum(1 for p in files if p.suffix.lower() == ".dcm")
    return total, dcm


def safe_stderr_tail(text: str, max_lines: int = 5) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    return " | ".join(lines[-max_lines:])


def extract_one_cab(cab_path: Path, dest_subdir: Path) -> tuple[bool, str, int, int, float]:
    start = time.perf_counter()
    dest_subdir.mkdir(parents=True, exist_ok=True)

    cmd = ["expand", "-R", str(cab_path), "-F:*", str(dest_subdir)]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    duration = time.perf_counter() - start
    total_files, total_dcm = count_extracted_files(dest_subdir)

    if proc.returncode == 0:
        return True, "", total_files, total_dcm, duration

    error_msg = safe_stderr_tail(proc.stderr)
    if not error_msg:
        error_msg = safe_stderr_tail(proc.stdout)
    if not error_msg:
        error_msg = f"expand exit code {proc.returncode}"

    return False, error_msg, total_files, total_dcm, duration


def write_report(report_path: Path, rows: list[ExtractionRow]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "timestamp": row.timestamp,
                    "source_cab": row.source_cab,
                    "source_path": row.source_path,
                    "output_subdir": row.output_subdir,
                    "extracted_files": row.extracted_files,
                    "extracted_dcm": row.extracted_dcm,
                    "status": row.status,
                    "error": row.error,
                    "duration_seconds": f"{row.duration_seconds:.3f}",
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract all .cab files from a scan folder into scan_extracted "
            "with one subfolder per CAB, then write extraction_report.csv"
        )
    )
    parser.add_argument(
        "scan_dir",
        type=Path,
        nargs="?",
        default=Path(r"C:\Users\Solutions\Desktop\dcm\dataset_chu_nice_2020_2021\scan"),
        help="Source scan directory containing CAB files",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(r"C:\Users\Solutions\Desktop\dcm\dataset_chu_nice_2020_2021\scan_extracted"),
        help="Destination root for extracted CAB contents",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(r"C:\Users\Solutions\Desktop\dcm\dataset_chu_nice_2020_2021\scan_extracted\extraction_report.csv"),
        help="CSV report path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N CAB files after sorting (for test runs)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scan_dir: Path = args.scan_dir
    out_dir: Path = args.out_dir
    report_path: Path = args.report
    limit: int | None = args.limit

    if not scan_dir.exists():
        print(f"ERROR: source folder not found: {scan_dir}")
        return 1

    cabs = find_cabs(scan_dir)
    if not cabs:
        print(f"No .cab files found in {scan_dir}")
        return 1

    if limit is not None:
        if limit <= 0:
            print("ERROR: --limit must be a positive integer")
            return 1
        cabs = cabs[:limit]

    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[ExtractionRow] = []
    global_start = time.perf_counter()

    total_cabs = len(cabs)
    print(f"Found {total_cabs} CAB file(s). Starting extraction...")

    for idx, cab_path in enumerate(cabs, start=1):
        subdir = out_dir / cab_path.stem
        print(f"[{idx}/{total_cabs}] Extracting {cab_path.name} -> {subdir.name}")

        ok, err, files_count, dcm_count, duration = extract_one_cab(cab_path, subdir)
        status = "success" if ok else "error"

        print(
            f"[{idx}/{total_cabs}] {status.upper()} | files={files_count} | "
            f"dcm={dcm_count} | duration={duration:.2f}s"
        )

        rows.append(
            ExtractionRow(
                timestamp=datetime.now().isoformat(timespec="seconds"),
                source_cab=cab_path.name,
                source_path=str(cab_path),
                output_subdir=str(subdir),
                extracted_files=files_count,
                extracted_dcm=dcm_count,
                status=status,
                error=err,
                duration_seconds=duration,
            )
        )

    write_report(report_path, rows)

    total_files = sum(r.extracted_files for r in rows)
    total_dcm = sum(r.extracted_dcm for r in rows)
    ok_count = sum(1 for r in rows if r.status == "success")
    err_count = total_cabs - ok_count
    elapsed = time.perf_counter() - global_start

    print("\nGlobal summary")
    print(f"CAB processed      : {total_cabs}")
    print(f"CAB success        : {ok_count}")
    print(f"CAB errors         : {err_count}")
    print(f"Extracted files    : {total_files}")
    print(f"Extracted .dcm     : {total_dcm}")
    print(f"Total duration (s) : {elapsed:.2f}")
    print(f"Report CSV         : {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
