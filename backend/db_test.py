
from sqlalchemy import text
from database import engine


def test_database_connection():
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT current_database(), version()")
            )

            database_name, database_version = result.fetchone()

            print("DUKAANTRA DATABASE CONNECTION SUCCESSFUL!")
            print(f"Database: {database_name}")
            print(f"Version: {database_version}")

    except Exception as error:
        print("DATABASE CONNECTION FAILED!")
        print(f"Error: {error}")


if __name__ == "__main__":
    test_database_connection()
