from __future__ import annotations

import argparse
import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# ---------------------------------------------------------------------------
# Reusable SQL snippets (substituted into queries via .format)
# ---------------------------------------------------------------------------
SNIPPETS = {
    "titled": "(Tit IS NOT NULL AND TRIM(Tit) <> '')",
    "wtitled": "(WTit IS NOT NULL AND TRIM(WTit) <> '')",
    "rated": "(CAST(NOV22 AS INTEGER) > 0)",
    "has_age": "(CAST(\"B-day\" AS INTEGER) > 1900)",
    "age": "(2022 - CAST(\"B-day\" AS INTEGER))",
    "active": "(Flag IS NULL OR TRIM(Flag) = '')",
}


@dataclass
class Query:
    section: str
    title: str
    sql: str


QUERIES: list[Query] = [
    # ------------------------------------------------------------------ overview
    Query("overview", "Dataset size and rated/titled counts", """
        SELECT COUNT(*) AS total_players,
               SUM({rated}) AS rated_players,
               SUM({titled}) AS open_titled,
               SUM({wtitled}) AS women_titled,
               COUNT(DISTINCT Fed) AS federations
        FROM {table}
    """),
    Query("overview", "Players by sex (all vs rated vs active)", """
        SELECT Sex,
               COUNT(*) AS players,
               SUM({rated}) AS rated,
               SUM({active}) AS active,
               ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM {table}), 2) AS pct_of_all
        FROM {table}
        GROUP BY Sex
    """),
    Query("overview", "Title distribution (open titles)", """
        SELECT TRIM(Tit) AS title, COUNT(*) AS players,
               ROUND(AVG(CASE WHEN {rated} THEN CAST(NOV22 AS INTEGER) END), 0) AS avg_rating
        FROM {table}
        WHERE {titled}
        GROUP BY TRIM(Tit)
        ORDER BY players DESC
    """),

    # ------------------------------------------------------------------ gender
    Query("gender", "Share of women at each open title", """
        SELECT TRIM(Tit) AS title,
               COUNT(*) AS total,
               SUM(Sex = 'F') AS women,
               ROUND(100.0 * SUM(Sex = 'F') / COUNT(*), 2) AS pct_women
        FROM {table}
        WHERE {titled}
        GROUP BY TRIM(Tit)
        ORDER BY total DESC
    """),
    Query("gender", "Share of women among rated players, by rating band", """
        SELECT CASE
                 WHEN r < 1000 THEN '<1000'
                 WHEN r < 1400 THEN '1000-1399'
                 WHEN r < 1800 THEN '1400-1799'
                 WHEN r < 2200 THEN '1800-2199'
                 WHEN r < 2500 THEN '2200-2499'
                 ELSE '2500+'
               END AS band,
               COUNT(*) AS players,
               SUM(Sex = 'F') AS women,
               ROUND(100.0 * SUM(Sex = 'F') / COUNT(*), 2) AS pct_women
        FROM (SELECT Sex, CAST(NOV22 AS INTEGER) AS r FROM {table} WHERE {rated})
        GROUP BY band
        ORDER BY MIN(r)
    """),
    Query("gender", "Rating summary by sex (rated players)", """
        SELECT Sex,
               COUNT(*) AS players,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 1) AS avg_rating,
               MIN(CAST(NOV22 AS INTEGER)) AS min_rating,
               MAX(CAST(NOV22 AS INTEGER)) AS max_rating
        FROM {table}
        WHERE {rated}
        GROUP BY Sex
    """),
    Query("gender", "Median rating by sex", """
        WITH ranked AS (
            SELECT Sex, CAST(NOV22 AS INTEGER) AS r,
                   ROW_NUMBER() OVER (PARTITION BY Sex ORDER BY CAST(NOV22 AS INTEGER)) AS rn,
                   COUNT(*) OVER (PARTITION BY Sex) AS cnt
            FROM {table} WHERE {rated}
        )
        SELECT Sex, AVG(r) AS median_rating, MAX(cnt) AS players
        FROM ranked
        WHERE rn IN ((cnt + 1) / 2, (cnt + 2) / 2)
        GROUP BY Sex
    """),
    Query("gender", "Top 10 men", """
        SELECT Name, Fed, TRIM(Tit) AS Tit, CAST(NOV22 AS INTEGER) AS rating, {age} AS age
        FROM {table}
        WHERE Sex = 'M' AND {rated}
        ORDER BY CAST(NOV22 AS INTEGER) DESC
        LIMIT 10
    """),
    Query("gender", "Top 10 women", """
        SELECT Name, Fed, TRIM(Tit) AS Tit, TRIM(WTit) AS WTit,
               CAST(NOV22 AS INTEGER) AS rating, {age} AS age
        FROM {table}
        WHERE Sex = 'F' AND {rated}
        ORDER BY CAST(NOV22 AS INTEGER) DESC
        LIMIT 10
    """),
    Query("gender", "Average rating of the top 10 / 100 by sex", """
        SELECT Sex, 'top 10' AS cohort, ROUND(AVG(r), 1) AS avg_rating FROM (
            SELECT Sex, CAST(NOV22 AS INTEGER) AS r, ROW_NUMBER() OVER
                (PARTITION BY Sex ORDER BY CAST(NOV22 AS INTEGER) DESC) AS rk
            FROM {table} WHERE {rated}) WHERE rk <= 10 GROUP BY Sex
        UNION ALL
        SELECT Sex, 'top 100', ROUND(AVG(r), 1) FROM (
            SELECT Sex, CAST(NOV22 AS INTEGER) AS r, ROW_NUMBER() OVER
                (PARTITION BY Sex ORDER BY CAST(NOV22 AS INTEGER) DESC) AS rk
            FROM {table} WHERE {rated}) WHERE rk <= 100 GROUP BY Sex
    """),
    Query("gender", "Share of each sex above rating thresholds", """
        SELECT Sex,
               COUNT(*) AS rated,
               ROUND(100.0 * SUM(CAST(NOV22 AS INTEGER) >= 2000) / COUNT(*), 2) AS pct_2000_plus,
               ROUND(100.0 * SUM(CAST(NOV22 AS INTEGER) >= 2200) / COUNT(*), 2) AS pct_2200_plus,
               ROUND(100.0 * SUM(CAST(NOV22 AS INTEGER) >= 2400) / COUNT(*), 2) AS pct_2400_plus,
               ROUND(100.0 * SUM(CAST(NOV22 AS INTEGER) >= 2500) / COUNT(*), 2) AS pct_2500_plus
        FROM {table}
        WHERE {rated}
        GROUP BY Sex
    """),
    Query("gender", "Average rating of titled players by sex and title", """
        SELECT TRIM(Tit) AS title, Sex, COUNT(*) AS players,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 1) AS avg_rating
        FROM {table}
        WHERE {titled} AND {rated}
        GROUP BY TRIM(Tit), Sex
        ORDER BY title, Sex
    """),
    Query("gender", "Women: open title vs women-only title", """
        SELECT CASE WHEN {titled} AND {wtitled} THEN 'Open + women title'
                    WHEN {titled} THEN 'Open title only'
                    ELSE 'Women title only' END AS holder_type,
               COUNT(*) AS players,
               ROUND(AVG(CASE WHEN {rated} THEN CAST(NOV22 AS INTEGER) END), 1) AS avg_rating
        FROM {table}
        WHERE Sex = 'F' AND ({titled} OR {wtitled})
        GROUP BY holder_type
    """),
    Query("gender", "Women's title (WGM etc.) holders and average rating", """
        SELECT TRIM(WTit) AS women_title, COUNT(*) AS players,
               ROUND(AVG(CASE WHEN {rated} THEN CAST(NOV22 AS INTEGER) END), 1) AS avg_rating,
               MIN(CASE WHEN {rated} THEN CAST(NOV22 AS INTEGER) END) AS min_rating
        FROM {table}
        WHERE {wtitled}
        GROUP BY TRIM(WTit)
        ORDER BY players DESC
    """),
    Query("gender", "Rating gap: lowest-rated GM men vs women", """
        SELECT Sex, COUNT(*) AS gms,
               MIN(CAST(NOV22 AS INTEGER)) AS lowest_rated_gm,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 1) AS avg_gm_rating
        FROM {table}
        WHERE TRIM(Tit) = 'GM' AND {rated}
        GROUP BY Sex
    """),

    # ------------------------------------------------------------------ activity
    Query("activity", "Games played and activity by sex (rated players)", """
        SELECT Sex,
               COUNT(*) AS players,
               ROUND(AVG(CAST(Gms AS INTEGER)), 2) AS avg_games,
               ROUND(100.0 * SUM(NOT {active}) / COUNT(*), 2) AS pct_inactive
        FROM {table}
        WHERE {rated}
        GROUP BY Sex
    """),
    Query("activity", "K-factor distribution by sex", """
        SELECT Sex, CAST(K AS INTEGER) AS k_factor, COUNT(*) AS players,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY Sex), 2) AS pct_of_sex
        FROM {table}
        WHERE K IS NOT NULL AND TRIM(K) <> ''
        GROUP BY Sex, CAST(K AS INTEGER)
        ORDER BY Sex, k_factor
    """),
    Query("activity", "Most active players (games in the period)", """
        SELECT Name, Fed, Sex, CAST(NOV22 AS INTEGER) AS rating, CAST(Gms AS INTEGER) AS games
        FROM {table}
        ORDER BY CAST(Gms AS INTEGER) DESC
        LIMIT 15
    """),

    # ------------------------------------------------------------------ age
    Query("age", "Average age and rating by title", """
        SELECT TRIM(Tit) AS title, COUNT(*) AS players,
               ROUND(AVG({age}), 1) AS avg_age,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 0) AS avg_rating
        FROM {table}
        WHERE {titled} AND {has_age} AND {rated}
        GROUP BY TRIM(Tit)
        ORDER BY avg_rating DESC
    """),
    Query("age", "Share of women by birth decade (pipeline / participation trend)", """
        SELECT (CAST("B-day" AS INTEGER) / 10) * 10 AS birth_decade,
               COUNT(*) AS players,
               SUM(Sex = 'F') AS women,
               ROUND(100.0 * SUM(Sex = 'F') / COUNT(*), 2) AS pct_women
        FROM {table}
        WHERE {has_age}
        GROUP BY birth_decade
        ORDER BY birth_decade
    """),
    Query("age", "Average rating by age group and sex", """
        SELECT CASE WHEN a < 18 THEN '<18' WHEN a < 30 THEN '18-29'
                    WHEN a < 45 THEN '30-44' WHEN a < 60 THEN '45-59'
                    ELSE '60+' END AS age_group,
               Sex, COUNT(*) AS players,
               ROUND(AVG(r), 1) AS avg_rating
        FROM (SELECT Sex, {age} AS a, CAST(NOV22 AS INTEGER) AS r
              FROM {table} WHERE {has_age} AND {rated})
        GROUP BY age_group, Sex
        ORDER BY MIN(a), Sex
    """),
    Query("age", "Youngest grandmasters", """
        SELECT Name, Fed, Sex, {age} AS age, CAST(NOV22 AS INTEGER) AS rating
        FROM {table}
        WHERE TRIM(Tit) = 'GM' AND {has_age}
        ORDER BY age ASC
        LIMIT 15
    """),
    Query("age", "Oldest active titled players", """
        SELECT Name, Fed, TRIM(Tit) AS Tit, {age} AS age, CAST(NOV22 AS INTEGER) AS rating
        FROM {table}
        WHERE {titled} AND {has_age} AND {active} AND {rated}
        ORDER BY age DESC
        LIMIT 15
    """),

    # ------------------------------------------------------------------ federations
    Query("federation", "Top 15 federations by number of GMs", """
        SELECT Fed, COUNT(*) AS gms,
               SUM(Sex = 'F') AS women_gms,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 0) AS avg_gm_rating
        FROM {table}
        WHERE TRIM(Tit) = 'GM'
        GROUP BY Fed
        ORDER BY gms DESC
        LIMIT 15
    """),
    Query("federation", "Federations with highest share of women (min 500 players)", """
        SELECT Fed, COUNT(*) AS players, SUM(Sex = 'F') AS women,
               ROUND(100.0 * SUM(Sex = 'F') / COUNT(*), 2) AS pct_women
        FROM {table}
        GROUP BY Fed
        HAVING COUNT(*) >= 500
        ORDER BY pct_women DESC
        LIMIT 15
    """),
    Query("federation", "Federations with lowest share of women (min 500 players)", """
        SELECT Fed, COUNT(*) AS players, SUM(Sex = 'F') AS women,
               ROUND(100.0 * SUM(Sex = 'F') / COUNT(*), 2) AS pct_women
        FROM {table}
        GROUP BY Fed
        HAVING COUNT(*) >= 500
        ORDER BY pct_women ASC
        LIMIT 15
    """),
    Query("federation", "Federations with the highest average rating (min 200 rated)", """
        SELECT Fed, COUNT(*) AS rated_players,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 1) AS avg_rating
        FROM {table}
        WHERE {rated}
        GROUP BY Fed
        HAVING COUNT(*) >= 200
        ORDER BY avg_rating DESC
        LIMIT 15
    """),
    Query("federation", "Gender rating gap by federation (min 50 rated women)", """
        SELECT Fed,
               SUM(Sex = 'F') AS women,
               ROUND(AVG(CASE WHEN Sex = 'M' THEN CAST(NOV22 AS INTEGER) END), 1) AS avg_men,
               ROUND(AVG(CASE WHEN Sex = 'F' THEN CAST(NOV22 AS INTEGER) END), 1) AS avg_women,
               ROUND(AVG(CASE WHEN Sex = 'M' THEN CAST(NOV22 AS INTEGER) END)
                   - AVG(CASE WHEN Sex = 'F' THEN CAST(NOV22 AS INTEGER) END), 1) AS gap
        FROM {table}
        WHERE {rated}
        GROUP BY Fed
        HAVING SUM(Sex = 'F') >= 50
        ORDER BY gap DESC
    """),

    # ------------------------------------------------------------------ titles / oddities
    Query("titles", "Players who hold a title but are rated unusually low (GM < 2300)", """
        SELECT Name, Fed, Sex, TRIM(Tit) AS Tit, CAST(NOV22 AS INTEGER) AS rating, {age} AS age
        FROM {table}
        WHERE TRIM(Tit) = 'GM' AND {rated} AND CAST(NOV22 AS INTEGER) < 2300
        ORDER BY rating ASC
        LIMIT 15
    """),
    Query("titles", "Untitled players rated 2500+ (no open title)", """
        SELECT Name, Fed, Sex, CAST(NOV22 AS INTEGER) AS rating, {age} AS age
        FROM {table}
        WHERE NOT {titled} AND {rated} AND CAST(NOV22 AS INTEGER) >= 2500
        ORDER BY rating DESC
    """),
    Query("titles", "Players holding multiple title types (open + women + other)", """
        SELECT Name, Fed, Sex, TRIM(Tit) AS Tit, TRIM(WTit) AS WTit, TRIM(OTit) AS OTit,
               CAST(NOV22 AS INTEGER) AS rating
        FROM {table}
        WHERE {titled} AND {wtitled} AND OTit IS NOT NULL AND TRIM(OTit) <> ''
        ORDER BY rating DESC
        LIMIT 20
    """),
    Query("titles", "Online arena (FOA) titles by sex", """
        SELECT TRIM(FOA) AS foa_title, Sex, COUNT(*) AS players
        FROM {table}
        WHERE FOA IS NOT NULL AND TRIM(FOA) <> ''
        GROUP BY TRIM(FOA), Sex
        ORDER BY foa_title, Sex
    """),
    Query("titles", "Most common names among titled players", """
        SELECT SUBSTR(TRIM(Name), INSTR(TRIM(Name), ',') + 2) AS first_name,
               COUNT(*) AS titled_players
        FROM {table}
        WHERE {titled} AND INSTR(Name, ',') > 0
        GROUP BY first_name
        ORDER BY titled_players DESC
        LIMIT 15
    """),
]


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run chess ratings analysis queries.")
    p.add_argument("--db", type=Path, default=Path("chess_ratings.db"))
    p.add_argument("--table", default=None,
                   help="Table name (default: 'ratings', or the only table in the DB)")
    p.add_argument("--list", action="store_true", help="List queries and exit")
    p.add_argument("--only", type=int, nargs="+", metavar="N", help="Run only these query numbers")
    p.add_argument("--section", help="Run only one section (overview, gender, activity, age, federation, titles)")
    p.add_argument("--export", type=Path, metavar="DIR", help="Save each result as a CSV in DIR")
    p.add_argument("--max-rows", type=int, default=30, help="Max rows to print per query (default 30)")
    return p.parse_args()


def resolve_table(conn: sqlite3.Connection, requested: str | None) -> str:
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    if requested:
        if requested not in tables:
            raise SystemExit(f"Table '{requested}' not found. Available: {tables}")
        return requested
    if "ratings" in tables:
        return "ratings"
    if len(tables) == 1:
        return tables[0]
    raise SystemExit(f"Specify --table. Available: {tables}")


def print_table(headers: Sequence[str], rows: Sequence[Sequence], max_rows: int) -> None:
    if not rows:
        print("  (no rows)")
        return
    shown = rows[:max_rows]
    str_rows = [["" if v is None else str(v) for v in r] for r in shown]
    widths = [max(len(h), *(len(r[i]) for r in str_rows)) for i, h in enumerate(headers)]
    fmt = lambda vals: " | ".join(v.ljust(widths[i]) for i, v in enumerate(vals))
    print("  " + fmt(headers))
    print("  " + "-+-".join("-" * w for w in widths))
    for r in str_rows:
        print("  " + fmt(r))
    if len(rows) > max_rows:
        print(f"  ... {len(rows) - max_rows} more row(s) not shown")


def export_csv(path: Path, headers: Sequence[str], rows: Sequence[Sequence]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def slugify(text: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in text).strip("_")[:60]


def main() -> None:
    args = parse_args()

    selected = list(enumerate(QUERIES, start=1))
    if args.only:
        selected = [(i, q) for i, q in selected if i in set(args.only)]
    if args.section:
        selected = [(i, q) for i, q in selected if q.section == args.section.lower()]

    if args.list:
        current = None
        for i, q in selected:
            if q.section != current:
                current = q.section
                print(f"\n[{current}]")
            print(f"  {i:>2}. {q.title}")
        return

    if not args.db.is_file():
        raise FileNotFoundError(f"Database file not found: {args.db}")

    conn = sqlite3.connect(args.db)
    table = resolve_table(conn, args.table)
    if args.export:
        args.export.mkdir(parents=True, exist_ok=True)

    for i, q in selected:
        sql = q.sql.format(table=table, **SNIPPETS)
        print(f"\n=== [{i}] ({q.section}) {q.title} ===")
        try:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            headers = [c[0] for c in cur.description]
        except sqlite3.Error as exc:
            print(f"  SQLite error: {exc}")
            continue
        print_table(headers, rows, args.max_rows)
        if args.export:
            export_csv(args.export / f"{i:02d}_{slugify(q.title)}.csv", headers, rows)

    conn.close()


if __name__ == "__main__":
    main()