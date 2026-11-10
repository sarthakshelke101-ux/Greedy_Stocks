
from sqlalchemy import text
from database import engine


def test_database_connection():
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text(
                    "SELECT DATABASE(), VERSION(), CURRENT_USER()"
                )
            )

            database, version, user = result.fetchone()

            print("GREEDY STOCKS DATABASE CONNECTION SUCCESSFUL!")
            print("---------------------------------------------")
            print(f"Database: {database}")
            print(f"MySQL Version: {version}")
            print(f"Connected User: {user}")

    except Exception as error:
        print("DATABASE CONNECTION FAILED!")
        print(f"Error: {error}")
        raise


if __name__ == "__main__":
    test_database_connection()
