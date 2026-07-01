import os
import sqlite3
import json
from datetime import datetime

# Set up the database path
DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DB_PATH = os.path.join(DB_DIR, "database.sqlite")

def get_db_connection():
    """Establish a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create data directories and initialize database tables if they do not exist."""
    # Ensure directories exist
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(os.path.join(DB_DIR, "downloads"), exist_ok=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Create articles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            link TEXT UNIQUE NOT NULL,
            pub_date TEXT NOT NULL,
            fetch_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            summary TEXT,
            impact TEXT,
            raw_text TEXT,
            attachments TEXT  -- JSON string of downloaded local file paths
        )
    """)
    
    # 2. Create indicators table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER,
            indicator_key TEXT NOT NULL,
            indicator_name TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT,
            period TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE,
            UNIQUE(indicator_key, period) ON CONFLICT REPLACE
        )
    """)
    
    conn.commit()
    conn.close()
    print("Database initialized successfully at:", DB_PATH)

if __name__ == "__main__":
    init_db()
