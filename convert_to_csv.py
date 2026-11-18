#!/usr/bin/env python3

"""Convert fixed-width text tables into CSV files.

This script infers column boundaries from the header row by finding stretches
of non-space characters. It is designed for files like the FRL snapshots in
this repository where columns are separated by aligned spaces.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import List, Sequence, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a fixed-width text file into CSV."
    )
    parser.add_argument("input_file", type=Path, help="Path to input .txt file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output .csv path (default: same name as input with .csv extension)",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="File encoding for reading and writing (default: utf-8)",
    )
    return parser.parse_args()


def find_column_layout(header_line: str) -> Tuple[List[str], List[Tuple[int, int]]]:
    rating_match = re.search(r"\b[A-Z]{3}\d{2}\b", header_line)
    if not rating_match:
        raise ValueError("Could not find rating column (for example, NOV16) in header.")

    column_names = [
        "ID Number",
        "Name",
        "Fed",
        "Sex",
        "Tit",
        "WTit",
        "OTit",
        "FOA",
        rating_match.group(0),
        "Gms",
        "K",
        "B-day",
        "Flag",
    ]

    starts = [
        header_line.find("ID Number"),
        header_line.find("Name"),
        header_line.find("Fed"),
        header_line.find("Sex"),
        header_line.find("Tit"),
        header_line.find("WTit"),
        header_line.find("OTit"),
        header_line.find("FOA"),
        rating_match.start(),
        header_line.find("Gms"),
        header_line.find("K"),
        header_line.find("B-day"),
        header_line.find("Flag"),
    ]

    if any(start < 0 for start in starts):
        raise ValueError("Could not detect all expected columns from header.")

    spans: List[Tuple[int, int]] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i < len(starts) - 1 else len(header_line)
        spans.append((start, end))

    return column_names, spans


def slice_row(line: str, spans: Sequence[Tuple[int, int]]) -> List[str]:
    return [line[start:end].strip() for start, end in spans]


def convert_fixed_width_to_csv(
    input_path: Path, output_path: Path, encoding: str = "utf-8"
) -> int:
    with input_path.open("r", encoding=encoding, errors="replace") as infile:
        lines = [line.rstrip("\n") for line in infile if line.strip()]

    if not lines:
        raise ValueError("Input file is empty.")

    header = lines[0]
    column_names, spans = find_column_layout(header)

    rows = [column_names]
    for line in lines[1:]:
        # Protect against short lines by padding to expected width.
        padded = line.ljust(len(header))
        rows.append(slice_row(padded, spans))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding=encoding) as outfile:
        writer = csv.writer(outfile)
        writer.writerows(rows)

    return len(rows) - 1


def main() -> None:
    args = parse_args()
    input_path: Path = args.input_file

    if not input_path.exists() or not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_path = args.output or input_path.with_suffix(".csv")
    record_count = convert_fixed_width_to_csv(input_path, output_path, args.encoding)

    print(f"Wrote {record_count} records to {output_path}")


if __name__ == "__main__":
    main()