#!/usr/bin/env python3

"""Remove rows where the Tit column is blank from a CSV file."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove rows where the Tit column is empty."
    )
    parser.add_argument("input_file", type=Path, help="Path to input CSV file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output CSV path (default: <input_stem>_titled.csv)",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="File encoding for reading and writing (default: utf-8)",
    )
    return parser.parse_args()


def remove_blank_tit_rows(
    input_path: Path, output_path: Path, encoding: str = "utf-8"
) -> tuple[int, int]:
    with input_path.open("r", newline="", encoding=encoding) as infile:
        reader = csv.DictReader(infile)
        if reader.fieldnames is None:
            raise ValueError("Input CSV has no header row.")
        if "Tit" not in reader.fieldnames:
            raise ValueError("Input CSV does not contain a 'Tit' column.")

        kept_rows: list[dict[str, str]] = []
        removed_count = 0
        for row in reader:
            if (row.get("Tit") or "").strip():
                kept_rows.append(row)
            else:
                removed_count += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding=encoding) as outfile:
        writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(kept_rows)

    return len(kept_rows), removed_count


def main() -> None:
    args = parse_args()
    input_path: Path = args.input_file

    if not input_path.exists() or not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_path = args.output or input_path.with_name(f"{input_path.stem}_titled.csv")
    kept, removed = remove_blank_tit_rows(input_path, output_path, args.encoding)

    print(f"Wrote {kept} rows to {output_path}")
    print(f"Removed {removed} rows with blank Tit values")


if __name__ == "__main__":
    main()