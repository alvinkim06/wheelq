
# clear.py
from sqlalchemy import text
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    engine = db.engine

    # Confirm the database before deleting anything
    print("Database:", engine.url.render_as_string(hide_password=True))
    print("Engine:", engine.dialect.name)

    confirm = input(
        "This will DELETE ALL database records. "
        "Type DELETE ALL to continue: "
    )

    if confirm != "DELETE ALL":
        print("Cancelled. No records were deleted.")
    else:
        # Back up your database file before running this script.
        with engine.connect() as connection:
            connection.execute(text("PRAGMA foreign_keys=OFF"))
            connection.commit()

            try:
                with connection.begin():
                    tables = reversed(db.metadata.sorted_tables)

                    for table in tables:
                        connection.execute(table.delete())
                        print(f"Cleared: {table.name}")

                    # Reset auto-increment counters if this table exists
                    has_sequence = connection.execute(
                        text("""
                            SELECT COUNT(*)
                            FROM sqlite_master
                            WHERE type = 'table'
                            AND name = 'sqlite_sequence'
                        """)
                    ).scalar_one()

                    if has_sequence:
                        connection.execute(
                            text("DELETE FROM sqlite_sequence")
                        )

                print("All registered table records cleared.")
            finally:
                with engine.connect() as fk_connection:
                    fk_connection.execute(
                        text("PRAGMA foreign_keys=ON")
                    )

            print("Database schema preserved.")


