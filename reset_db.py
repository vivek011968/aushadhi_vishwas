import sqlite3
import os

DB_FILE = 'database.db'

def reset_db():
    if os.path.exists(DB_FILE):
        print(f"Removing old database: {DB_FILE}")
        os.remove(DB_FILE)
    
    print("Initializing new optimized database...")
    from app import init_db
    init_db()
    print("Database reset and optimized successfully!")

if __name__ == "__main__":
    reset_db()
