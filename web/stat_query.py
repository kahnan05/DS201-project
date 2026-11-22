import sqlite3
import csv
from pathlib import Path

# This is the name of the database file.
DATABASE = "chess_ratings.db"

# This is the name of the table inside the database.
TABLE = "ratings"

# Each item contains a section name, a query title, and the SQL query.
# The SQL is written out directly so it is easier to follow and edit.

queries = [

    # OVERVIEW QUERIES

    ("overview", "Dataset size and rated/titled counts", """
        SELECT COUNT(*) AS total_players,
               SUM(CASE WHEN CAST(NOV22 AS INTEGER) > 0 THEN 1 ELSE 0 END) AS rated_players,
               SUM(CASE WHEN Tit IS NOT NULL AND TRIM(Tit) <> '' THEN 1 ELSE 0 END) AS open_titled,
               SUM(CASE WHEN WTit IS NOT NULL AND TRIM(WTit) <> '' THEN 1 ELSE 0 END) AS women_titled,
               COUNT(DISTINCT Fed) AS federations
        FROM ratings
    """),

    ("overview", "Players by sex (all vs rated vs active)", """
        SELECT Sex,
               COUNT(*) AS players,
               SUM(CASE WHEN CAST(NOV22 AS INTEGER) > 0 THEN 1 ELSE 0 END) AS rated,
               SUM(CASE WHEN Flag IS NULL OR TRIM(Flag) = '' THEN 1 ELSE 0 END) AS active,
               ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM ratings), 2) AS pct_of_all
        FROM ratings
        GROUP BY Sex
    """),

    ("overview", "Title distribution (open titles)", """
        SELECT TRIM(Tit) AS title,
               COUNT(*) AS players,
               ROUND(AVG(CASE WHEN CAST(NOV22 AS INTEGER) > 0
                              THEN CAST(NOV22 AS INTEGER) END), 0) AS avg_rating
        FROM ratings
        WHERE Tit IS NOT NULL AND TRIM(Tit) <> ''
        GROUP BY TRIM(Tit)
        ORDER BY players DESC
    """),

    # GENDER QUERIES

    ("gender", "Share of women at each open title", """
        SELECT TRIM(Tit) AS title,
               COUNT(*) AS total,
               SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) AS women,
               ROUND(100.0 * SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_women
        FROM ratings
        WHERE Tit IS NOT NULL AND TRIM(Tit) <> ''
        GROUP BY TRIM(Tit)
        ORDER BY total DESC
    """),

    ("gender", "Share of women among rated players, by rating band", """
        SELECT CASE
                   WHEN rating < 1000 THEN '<1000'
                   WHEN rating < 1400 THEN '1000-1399'
                   WHEN rating < 1800 THEN '1400-1799'
                   WHEN rating < 2200 THEN '1800-2199'
                   WHEN rating < 2500 THEN '2200-2499'
                   ELSE '2500+'
               END AS band,
               COUNT(*) AS players,
               SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) AS women,
               ROUND(100.0 * SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_women
        FROM (
            SELECT Sex, CAST(NOV22 AS INTEGER) AS rating
            FROM ratings
            WHERE CAST(NOV22 AS INTEGER) > 0
        )
        GROUP BY band
        ORDER BY MIN(rating)
    """),

    ("gender", "Rating summary by sex (rated players)", """
        SELECT Sex,
               COUNT(*) AS players,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 1) AS avg_rating,
               MIN(CAST(NOV22 AS INTEGER)) AS min_rating,
               MAX(CAST(NOV22 AS INTEGER)) AS max_rating
        FROM ratings
        WHERE CAST(NOV22 AS INTEGER) > 0
        GROUP BY Sex
    """),

    ("gender", "Median rating by sex", """
        WITH ranked AS (
            SELECT Sex,
                   CAST(NOV22 AS INTEGER) AS rating,
                   ROW_NUMBER() OVER (
                       PARTITION BY Sex
                       ORDER BY CAST(NOV22 AS INTEGER)
                   ) AS row_number,
                   COUNT(*) OVER (PARTITION BY Sex) AS player_count
            FROM ratings
            WHERE CAST(NOV22 AS INTEGER) > 0
        )
        SELECT Sex,
               AVG(rating) AS median_rating,
               MAX(player_count) AS players
        FROM ranked
        WHERE row_number IN ((player_count + 1) / 2, (player_count + 2) / 2)
        GROUP BY Sex
    """),

    ("gender", "Top 10 men", """
        SELECT Name, Fed, TRIM(Tit) AS Tit,
               CAST(NOV22 AS INTEGER) AS rating,
               2022 - CAST("B-day" AS INTEGER) AS age
        FROM ratings
        WHERE Sex = 'M'
          AND CAST(NOV22 AS INTEGER) > 0
          AND CAST("B-day" AS INTEGER) > 1900
        ORDER BY CAST(NOV22 AS INTEGER) DESC
        LIMIT 10
    """),

    ("gender", "Top 10 women", """
        SELECT Name, Fed, TRIM(Tit) AS Tit, TRIM(WTit) AS WTit,
               CAST(NOV22 AS INTEGER) AS rating,
               2022 - CAST("B-day" AS INTEGER) AS age
        FROM ratings
        WHERE Sex = 'F'
          AND CAST(NOV22 AS INTEGER) > 0
          AND CAST("B-day" AS INTEGER) > 1900
        ORDER BY CAST(NOV22 AS INTEGER) DESC
        LIMIT 10
    """),

    ("gender", "Average rating of the top 10 / 100 by sex", """
        SELECT Sex, 'top 10' AS group_name, ROUND(AVG(rating), 1) AS avg_rating
        FROM (
            SELECT Sex, CAST(NOV22 AS INTEGER) AS rating,
                   ROW_NUMBER() OVER (
                       PARTITION BY Sex
                       ORDER BY CAST(NOV22 AS INTEGER) DESC
                   ) AS rank_number
            FROM ratings
            WHERE CAST(NOV22 AS INTEGER) > 0
        )
        WHERE rank_number <= 10
        GROUP BY Sex

        UNION ALL

        SELECT Sex, 'top 100' AS group_name, ROUND(AVG(rating), 1) AS avg_rating
        FROM (
            SELECT Sex, CAST(NOV22 AS INTEGER) AS rating,
                   ROW_NUMBER() OVER (
                       PARTITION BY Sex
                       ORDER BY CAST(NOV22 AS INTEGER) DESC
                   ) AS rank_number
            FROM ratings
            WHERE CAST(NOV22 AS INTEGER) > 0
        )
        WHERE rank_number <= 100
        GROUP BY Sex
    """),

    ("gender", "Share of each sex above rating thresholds", """
        SELECT Sex,
               COUNT(*) AS rated_players,
               ROUND(100.0 * SUM(CASE WHEN CAST(NOV22 AS INTEGER) >= 2000 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_2000_plus,
               ROUND(100.0 * SUM(CASE WHEN CAST(NOV22 AS INTEGER) >= 2200 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_2200_plus,
               ROUND(100.0 * SUM(CASE WHEN CAST(NOV22 AS INTEGER) >= 2400 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_2400_plus,
               ROUND(100.0 * SUM(CASE WHEN CAST(NOV22 AS INTEGER) >= 2500 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_2500_plus
        FROM ratings
        WHERE CAST(NOV22 AS INTEGER) > 0
        GROUP BY Sex
    """),

    ("gender", "Average rating of titled players by sex and title", """
        SELECT TRIM(Tit) AS title,
               Sex,
               COUNT(*) AS players,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 1) AS avg_rating
        FROM ratings
        WHERE Tit IS NOT NULL AND TRIM(Tit) <> ''
          AND CAST(NOV22 AS INTEGER) > 0
        GROUP BY TRIM(Tit), Sex
        ORDER BY title, Sex
    """),

    ("gender", "Women: open title vs women-only title", """
        SELECT CASE
                   WHEN Tit IS NOT NULL AND TRIM(Tit) <> ''
                    AND WTit IS NOT NULL AND TRIM(WTit) <> ''
                       THEN 'Open + women title'
                   WHEN Tit IS NOT NULL AND TRIM(Tit) <> ''
                       THEN 'Open title only'
                   ELSE 'Women title only'
               END AS holder_type,
               COUNT(*) AS players,
               ROUND(AVG(CASE WHEN CAST(NOV22 AS INTEGER) > 0
                              THEN CAST(NOV22 AS INTEGER) END), 1) AS avg_rating
        FROM ratings
        WHERE Sex = 'F'
          AND ((Tit IS NOT NULL AND TRIM(Tit) <> '')
            OR (WTit IS NOT NULL AND TRIM(WTit) <> ''))
        GROUP BY holder_type
    """),

    ("gender", "Women's title holders and average rating", """
        SELECT TRIM(WTit) AS women_title,
               COUNT(*) AS players,
               ROUND(AVG(CASE WHEN CAST(NOV22 AS INTEGER) > 0
                              THEN CAST(NOV22 AS INTEGER) END), 1) AS avg_rating,
               MIN(CASE WHEN CAST(NOV22 AS INTEGER) > 0
                        THEN CAST(NOV22 AS INTEGER) END) AS min_rating
        FROM ratings
        WHERE WTit IS NOT NULL AND TRIM(WTit) <> ''
        GROUP BY TRIM(WTit)
        ORDER BY players DESC
    """),

    ("gender", "Rating comparison of male and female grandmasters", """
        SELECT Sex,
               COUNT(*) AS grandmasters,
               MIN(CAST(NOV22 AS INTEGER)) AS lowest_rating,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 1) AS avg_rating
        FROM ratings
        WHERE TRIM(Tit) = 'GM'
          AND CAST(NOV22 AS INTEGER) > 0
        GROUP BY Sex
    """),

    # ACTIVITY QUERIES

    ("activity", "Games played and activity by sex (rated players)", """
        SELECT Sex,
               COUNT(*) AS players,
               ROUND(AVG(CAST(Gms AS INTEGER)), 2) AS avg_games,
               ROUND(100.0 * SUM(CASE WHEN Flag IS NOT NULL AND TRIM(Flag) <> ''
                                      THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_inactive
        FROM ratings
        WHERE CAST(NOV22 AS INTEGER) > 0
        GROUP BY Sex
    """),

    ("activity", "K-factor distribution by sex", """
        SELECT Sex,
               CAST(K AS INTEGER) AS k_factor,
               COUNT(*) AS players,
               ROUND(
                   100.0 * COUNT(*) /
                   SUM(COUNT(*)) OVER (PARTITION BY Sex), 2
               ) AS pct_of_sex
        FROM ratings
        WHERE K IS NOT NULL AND TRIM(K) <> ''
        GROUP BY Sex, CAST(K AS INTEGER)
        ORDER BY Sex, k_factor
    """),

    ("activity", "Most active players (games in the period)", """
        SELECT Name, Fed, Sex,
               CAST(NOV22 AS INTEGER) AS rating,
               CAST(Gms AS INTEGER) AS games
        FROM ratings
        WHERE Gms IS NOT NULL AND TRIM(Gms) <> ''
        ORDER BY CAST(Gms AS INTEGER) DESC
        LIMIT 15
    """),

    # AGE QUERIES

    ("age", "Average age and rating by title", """
        SELECT TRIM(Tit) AS title,
               COUNT(*) AS players,
               ROUND(AVG(2022 - CAST("B-day" AS INTEGER)), 1) AS avg_age,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 0) AS avg_rating
        FROM ratings
        WHERE Tit IS NOT NULL AND TRIM(Tit) <> ''
          AND CAST("B-day" AS INTEGER) > 1900
          AND CAST(NOV22 AS INTEGER) > 0
        GROUP BY TRIM(Tit)
        ORDER BY avg_rating DESC
    """),

    ("age", "Share of women by birth decade", """
        SELECT (CAST("B-day" AS INTEGER) / 10) * 10 AS birth_decade,
               COUNT(*) AS players,
               SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) AS women,
               ROUND(100.0 * SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_women
        FROM ratings
        WHERE CAST("B-day" AS INTEGER) > 1900
        GROUP BY birth_decade
        ORDER BY birth_decade
    """),

    ("age", "Average rating by age group and sex", """
        SELECT CASE
                   WHEN age < 18 THEN '<18'
                   WHEN age < 30 THEN '18-29'
                   WHEN age < 45 THEN '30-44'
                   WHEN age < 60 THEN '45-59'
                   ELSE '60+'
               END AS age_group,
               Sex,
               COUNT(*) AS players,
               ROUND(AVG(rating), 1) AS avg_rating
        FROM (
            SELECT Sex,
                   2022 - CAST("B-day" AS INTEGER) AS age,
                   CAST(NOV22 AS INTEGER) AS rating
            FROM ratings
            WHERE CAST("B-day" AS INTEGER) > 1900
              AND CAST(NOV22 AS INTEGER) > 0
        )
        GROUP BY age_group, Sex
        ORDER BY MIN(age), Sex
    """),

    ("age", "Youngest grandmasters", """
        SELECT Name, Fed, Sex,
               2022 - CAST("B-day" AS INTEGER) AS age,
               CAST(NOV22 AS INTEGER) AS rating
        FROM ratings
        WHERE TRIM(Tit) = 'GM'
          AND CAST("B-day" AS INTEGER) > 1900
        ORDER BY age ASC
        LIMIT 15
    """),

    ("age", "Oldest active titled players", """
        SELECT Name, Fed, TRIM(Tit) AS Tit,
               2022 - CAST("B-day" AS INTEGER) AS age,
               CAST(NOV22 AS INTEGER) AS rating
        FROM ratings
        WHERE Tit IS NOT NULL AND TRIM(Tit) <> ''
          AND CAST("B-day" AS INTEGER) > 1900
          AND (Flag IS NULL OR TRIM(Flag) = '')
          AND CAST(NOV22 AS INTEGER) > 0
        ORDER BY age DESC
        LIMIT 15
    """),

    # FEDERATION QUERIES

    ("federation", "Top 15 federations by number of GMs", """
        SELECT Fed,
               COUNT(*) AS gms,
               SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) AS women_gms,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 0) AS avg_gm_rating
        FROM ratings
        WHERE TRIM(Tit) = 'GM'
          AND CAST(NOV22 AS INTEGER) > 0
        GROUP BY Fed
        ORDER BY gms DESC
        LIMIT 15
    """),

    ("federation", "Federations with highest share of women (minimum 500 players)", """
        SELECT Fed,
               COUNT(*) AS players,
               SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) AS women,
               ROUND(100.0 * SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_women
        FROM ratings
        GROUP BY Fed
        HAVING COUNT(*) >= 500
        ORDER BY pct_women DESC
        LIMIT 15
    """),

    ("federation", "Federations with lowest share of women (minimum 500 players)", """
        SELECT Fed,
               COUNT(*) AS players,
               SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) AS women,
               ROUND(100.0 * SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_women
        FROM ratings
        GROUP BY Fed
        HAVING COUNT(*) >= 500
        ORDER BY pct_women ASC
        LIMIT 15
    """),

    ("federation", "Federations with the highest average rating (minimum 200 rated players)", """
        SELECT Fed,
               COUNT(*) AS rated_players,
               ROUND(AVG(CAST(NOV22 AS INTEGER)), 1) AS avg_rating
        FROM ratings
        WHERE CAST(NOV22 AS INTEGER) > 0
        GROUP BY Fed
        HAVING COUNT(*) >= 200
        ORDER BY avg_rating DESC
        LIMIT 15
    """),

    ("federation", "Gender rating gap by federation (minimum 50 rated women)", """
        SELECT Fed,
               SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) AS women,
               ROUND(AVG(CASE WHEN Sex = 'M' THEN CAST(NOV22 AS INTEGER) END), 1) AS avg_men,
               ROUND(AVG(CASE WHEN Sex = 'F' THEN CAST(NOV22 AS INTEGER) END), 1) AS avg_women,
               ROUND(
                   AVG(CASE WHEN Sex = 'M' THEN CAST(NOV22 AS INTEGER) END) -
                   AVG(CASE WHEN Sex = 'F' THEN CAST(NOV22 AS INTEGER) END), 1
               ) AS rating_gap
        FROM ratings
        WHERE CAST(NOV22 AS INTEGER) > 0
        GROUP BY Fed
        HAVING SUM(CASE WHEN Sex = 'F' THEN 1 ELSE 0 END) >= 50
        ORDER BY rating_gap DESC
    """),

    # TITLE QUERIES

    ("titles", "Grandmasters rated below 2300", """
        SELECT Name, Fed, Sex, TRIM(Tit) AS Tit,
               CAST(NOV22 AS INTEGER) AS rating,
               2022 - CAST("B-day" AS INTEGER) AS age
        FROM ratings
        WHERE TRIM(Tit) = 'GM'
          AND CAST(NOV22 AS INTEGER) > 0
          AND CAST(NOV22 AS INTEGER) < 2300
          AND CAST("B-day" AS INTEGER) > 1900
        ORDER BY rating ASC
        LIMIT 15
    """),

    ("titles", "Untitled players rated 2500+ (no open title)", """
        SELECT Name, Fed, Sex,
               CAST(NOV22 AS INTEGER) AS rating,
               2022 - CAST("B-day" AS INTEGER) AS age
        FROM ratings
        WHERE (Tit IS NULL OR TRIM(Tit) = '')
          AND CAST(NOV22 AS INTEGER) >= 2500
          AND CAST("B-day" AS INTEGER) > 1900
        ORDER BY rating DESC
    """),

    ("titles", "Players holding multiple title types", """
        SELECT Name, Fed, Sex,
               TRIM(Tit) AS Tit,
               TRIM(WTit) AS WTit,
               TRIM(OTit) AS OTit,
               CAST(NOV22 AS INTEGER) AS rating
        FROM ratings
        WHERE Tit IS NOT NULL AND TRIM(Tit) <> ''
          AND WTit IS NOT NULL AND TRIM(WTit) <> ''
          AND OTit IS NOT NULL AND TRIM(OTit) <> ''
        ORDER BY rating DESC
        LIMIT 20
    """),

    ("titles", "Online arena (FOA) titles by sex", """
        SELECT TRIM(FOA) AS foa_title,
               Sex,
               COUNT(*) AS players
        FROM ratings
        WHERE FOA IS NOT NULL AND TRIM(FOA) <> ''
        GROUP BY TRIM(FOA), Sex
        ORDER BY foa_title, Sex
    """),

    ("titles", "Most common first names among titled players", """
        SELECT SUBSTR(TRIM(Name), INSTR(TRIM(Name), ',') + 2) AS first_name,
               COUNT(*) AS titled_players
        FROM ratings
        WHERE Tit IS NOT NULL AND TRIM(Tit) <> ''
          AND INSTR(Name, ',') > 0
        GROUP BY first_name
        ORDER BY titled_players DESC
        LIMIT 15
    """)
]


# This function prints the results in a simple table.
def print_results(column_names, rows, max_rows):
    if len(rows) == 0:
        print("  No results found.")
        return

    # Find the width needed for each column.
    column_widths = []
    for i in range(len(column_names)):
        widest = len(column_names[i])

        for row in rows[:max_rows]:
            value = "" if row[i] is None else str(row[i])
            if len(value) > widest:
                widest = len(value)

        column_widths.append(widest)

    # Print the column headings.
    heading = " | ".join(
        column_names[i].ljust(column_widths[i])
        for i in range(len(column_names))
    )
    print("  " + heading)
    print("  " + "-+-".join("-" * width for width in column_widths))

    # Print each row.
    for row in rows[:max_rows]:
        values = []
        for i in range(len(column_names)):
            value = "" if row[i] is None else str(row[i])
            values.append(value.ljust(column_widths[i]))

        print("  " + " | ".join(values))

    if len(rows) > max_rows:
        print("  ... " + str(len(rows) - max_rows) + " more rows not shown")


# This function saves query results as a CSV file.
def save_csv(file_name, column_names, rows):
    with open(file_name, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(column_names)
        writer.writerows(rows)


# Main part of the program.
def main():
    print("Chess Ratings Database Statistics")
    print("---------------------------------")

    # Connect to the database.
    connection = sqlite3.connect(DATABASE)

    # Ask which section the user wants to run.
    print("\nAvailable sections:")
    print("overview, gender, activity, age, federation, titles, all")

    section_choice = input("\nWhich section would you like to run? ").strip().lower()

    if section_choice == "":
        section_choice = "all"

    # Ask how many rows should be displayed.
    max_rows_input = input("Maximum number of rows to display (press Enter for 30): ").strip()

    if max_rows_input == "":
        max_rows = 30
    else:
        max_rows = int(max_rows_input)

    # Ask whether results should be saved as CSV files.
    export_choice = input("Save results as CSV files? (y/n): ").strip().lower()

    if export_choice == "y":
        output_folder = Path("query_results")
        output_folder.mkdir(exist_ok=True)
    else:
        output_folder = None

    # Run the selected queries.
    query_number = 0

    for query in queries:
        query_number += 1

        section = query[0]
        title = query[1]
        sql = query[2]

        if section_choice != "all" and section_choice != section:
            continue

        print("\n")
        print("Query " + str(query_number) + ": " + title)
        print("Section: " + section)

        try:
            cursor = connection.execute(sql)
            rows = cursor.fetchall()
            column_names = [description[0] for description in cursor.description]

            print_results(column_names, rows, max_rows)

            if output_folder is not None:
                file_name = output_folder / (
                    str(query_number).zfill(2) + "_" +
                    title.lower().replace(" ", "_").replace("/", "_") + ".csv"
                )
                save_csv(file_name, column_names, rows)
                print("Saved CSV: " + str(file_name))

        except sqlite3.Error as error:
            print("There was an error running this query:")
            print(error)

    # Close the database connection.
    connection.close()
    print("\nFinished running queries.")


if __name__ == "__main__":
    main()
