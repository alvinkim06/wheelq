import sqlite3

db_path = r"E:\Downloads\docs\DOCS\case\wheelq2\instance\wheelq.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Rename old table
cursor.execute("ALTER TABLE client RENAME TO client_old")

# Create new table with id and official_id
cursor.execute("""
CREATE TABLE client (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    official_id TEXT NOT NULL UNIQUE,
    name TEXT,
    email TEXT,
    phone TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# Copy old data (skip id, assign automatically; set dummy official_id if missing)
cursor.execute("""
INSERT INTO client (official_id, name, email, phone, created_at)
SELECT COALESCE(official_id, 'UNKNOWN'), name, email, phone, created_at
FROM client_old
""")

# Drop old table
cursor.execute("DROP TABLE client_old")

conn.commit()
conn.close()

print("Client table fixed successfully.")
