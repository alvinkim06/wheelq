from app import db
db.engine.execute("DROP TABLE IF EXISTS _alembic_tmp_booking;")
