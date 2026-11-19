#!/usr/bin/env python3

"""Interactive SQLite query tool for chess_ratings.db."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Iterable, Sequence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query a SQLite database using interactive SQL input."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("chess_ratings.db"),
        help="Path to SQLite database file (default: chess_ratings.db)",
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Run one SQL query and exit.",
    )
    return parser.parse_args()


def print_table(headers: Sequence[str], rows: Sequence[sqlite3.Row]) -> None:
    if not rows:
        print("No rows returned.")
        return

    str_rows = [["" if value is None else str(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in str_rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def format_row(values: Iterable[str]) -> str:
        return " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(values))

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in str_rows:
        print(format_row(row))


def execute_sql(conn: sqlite3.Connection, sql: str) -> None:
    sql = sql.strip()
    if not sql:
        return

    cursor = conn.execute(sql)

    first_keyword = sql.split(None, 1)[0].lower() if sql.split() else ""
    is_result_query = first_keyword in {"select", "with", "pragma", "explain"}

    if is_result_query and cursor.description is not None:
        rows = cursor.fetchall()
        headers = [col[0] for col in cursor.description]
        print_table(headers, rows)
        print(f"\n{len(rows)} row(s) returned.")
    else:
        conn.commit()
        changed = cursor.rowcount if cursor.rowcount >= 0 else 0
        print(f"Query OK. {changed} row(s) affected.")


def list_tables(conn: sqlite3.Connection) -> None:
    sql = """
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    ORDER BY name
    """
    rows = conn.execute(sql).fetchall()
    if not rows:
        print("No tables found.")
        return

    print("Tables:")
    for row in rows:
        print(f"- {row['name']}")


def show_schema(conn: sqlite3.Connection, table_name: str | None = None) -> None:
    if table_name:
        sql = "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?"
        row = conn.execute(sql, (table_name,)).fetchone()
        if row is None or row[0] is None:
            print(f"Table not found: {table_name}")
            return
        print(row[0])
        return

    sql = "SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name"
    rows = conn.execute(sql).fetchall()
    if not rows:
        print("No table schema found.")
        return

    for row in rows:
        if row[0]:
            print(row[0])
            print()


def interactive_shell(conn: sqlite3.Connection) -> None:
    print("Connected. Type SQL and end with ';' to run.")
    print("Commands: .tables, .schema [table], .help, .quit")

    buffer = ""
    while True:
        prompt = "sql> " if not buffer else "...> "
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return

        command = line.strip()
        if not buffer and command in {".quit", ".exit"}:
            print("Bye.")
            return
        if not buffer and command == ".help":
            print(".tables             List tables")
            print(".schema             Show all table schemas")
            print(".schema TABLE_NAME  Show one table schema")
            print(".quit               Exit")
            continue
        if not buffer and command == ".tables":
            list_tables(conn)
            continue
        if not buffer and command.startswith(".schema"):
            parts = command.split(maxsplit=1)
            table_name = parts[1] if len(parts) > 1 else None
            show_schema(conn, table_name)
            continue

        buffer = f"{buffer}\n{line}".strip()
        if sqlite3.complete_statement(buffer):
            try:
                execute_sql(conn, buffer)
            except sqlite3.Error as exc:
                print(f"SQLite error: {exc}")
            finally:
                buffer = ""


def main() -> None:
    args = parse_args()
    db_path = args.db

    if not db_path.exists() or not db_path.is_file():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        if args.query:
            execute_sql(conn, args.query)
        else:
            interactive_shell(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()