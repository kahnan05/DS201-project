import pandas as pd
import sqlite3
import os

# Folder containing the 33 CSV files
DATA_FOLDER = "data"

# Name of the SQLite database
DATABASE_NAME = "chess_ratings.db"

# Rating types and years
rating_types = ["standard", "blitz", "rapid"]
years = range(2016, 2027)

# Connect to the database
connection = sqlite3.connect(DATABASE_NAME)

all_data = []

# Loop through every rating type and year
for rating_type in rating_types:
    for year in years:

        year_short = str(year)[-2:]

        filename = f"{rating_type}_nov{year_short}frl_titled.csv"
        filepath = os.path.join(DATA_FOLDER, filename)

        # Check that the CSV file exists
        if not os.path.exists(filepath):
            print(f"File not found: {filename}")
            continue

        print(f"Loading {filename}...")

        # Read the CSV
        df = pd.read_csv(filepath, dtype={"ID Number": "string"})

        # Find the correct rating column
        rating_column = f"NOV{year_short}"

        if rating_column not in df.columns:
            print(f"Missing column {rating_column} in {filename}")
            continue

        # Rename columns
        df = df.rename(columns={
            "ID Number": "player_id",
            "Name": "name",
            "Fed": "federation",
            "Sex": "sex",
            "Tit": "title",
            "WTit": "women_title",
            "OTit": "other_title",
            "FOA": "foa",
            "Gms": "games",
            "K": "k_factor",
            "B-day": "birthday",
            "Flag": "flag",
            rating_column: "rating"
        })

        # Add year and rating type
        df["year"] = year
        df["rating_type"] = rating_type

        # Keep the columns we need
        columns = [
            "player_id",
            "name",
            "federation",
            "sex",
            "title",
            "women_title",
            "other_title",
            "foa",
            "rating",
            "games",
            "k_factor",
            "birthday",
            "flag",
            "year",
            "rating_type"
        ]

        df = df[columns]

        # Convert rating to numeric
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")

        # Remove rows without a player ID, federation, or rating
        df = df.dropna(subset=["player_id", "federation", "rating"])

        all_data.append(df)

# Combine all CSV files into one DataFrame
if all_data:

    combined_df = pd.concat(all_data, ignore_index=True)

    # Write everything into one SQL table
    combined_df.to_sql(
        "chess_ratings",
        connection,
        if_exists="replace",
        index=False
    )

    # Create indexes to make queries faster
    connection.execute("""
        CREATE INDEX idx_player_id
        ON chess_ratings (player_id)
    """)

    connection.execute("""
        CREATE INDEX idx_federation
        ON chess_ratings (federation)
    """)

    connection.execute("""
        CREATE INDEX idx_year
        ON chess_ratings (year)
    """)

    connection.execute("""
        CREATE INDEX idx_rating_type
        ON chess_ratings (rating_type)
    """)

    connection.commit()

    # Print database summary
    print("\nDatabase successfully created!")
    print(f"Total records: {len(combined_df):,}")

    print("\nRecords by rating type:")
    print(combined_df["rating_type"].value_counts())

    print("\nRecords by year:")
    print(combined_df["year"].value_counts().sort_index())

else:
    print("No data was loaded. Check your CSV files and folder path.")

# Close database connection
connection.close()

