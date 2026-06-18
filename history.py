import sqlite3
import json
from datetime import datetime

DB_PATH = "phoenixforge.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        idea TEXT NOT NULL,
        timestamp TEXT NOT NULL
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS raw_scrapes (
        analysis_id INTEGER PRIMARY KEY,
        full_scraped_text TEXT,
        FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS results (
        analysis_id INTEGER PRIMARY KEY,
        heatmap_json TEXT,
        fixes_json TEXT,
        graveyard_text TEXT,
        raw_content TEXT,
        FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
    );
    """)
    
    # SAFE SCHEMA MIGRATION: check results table columns and alter if missing
    try:
        cursor.execute("PRAGMA table_info(results)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "raw_combined_markdown" not in columns:
            print("Adding raw_combined_markdown column to results table...")
            cursor.execute("ALTER TABLE results ADD COLUMN raw_combined_markdown TEXT;")
            
        if "scraped_urls" not in columns:
            print("Adding scraped_urls column to results table...")
            cursor.execute("ALTER TABLE results ADD COLUMN scraped_urls TEXT;")
            
        if "source_count" not in columns:
            print("Adding source_count column to results table...")
            cursor.execute("ALTER TABLE results ADD COLUMN source_count INTEGER;")
            
        conn.commit()
    except Exception as e:
        print(f"Error during migration: {e}")
        
    conn.commit()
    conn.close()

def save_analysis(idea, full_scraped_text, heatmap_dict, fixes_list, graveyard_text, raw_content, raw_combined_markdown=None, scraped_urls=None, source_count=None):
    init_db()  # Ensure database and tables exist
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        timestamp = datetime.now().isoformat()
        
        # Insert into analyses
        cursor.execute(
            "INSERT INTO analyses (idea, timestamp) VALUES (?, ?);",
            (idea, timestamp)
        )
        analysis_id = cursor.lastrowid
        
        # Insert into raw_scrapes
        cursor.execute(
            "INSERT INTO raw_scrapes (analysis_id, full_scraped_text) VALUES (?, ?);",
            (analysis_id, full_scraped_text)
        )
        
        # Insert into results
        cursor.execute(
            """
            INSERT INTO results (analysis_id, heatmap_json, fixes_json, graveyard_text, raw_content, raw_combined_markdown, scraped_urls, source_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                analysis_id,
                json.dumps(heatmap_dict),
                json.dumps(fixes_list),
                graveyard_text,
                raw_content,
                raw_combined_markdown,
                json.dumps(scraped_urls) if scraped_urls is not None else None,
                source_count
            )
        )
        
        conn.commit()
        return analysis_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_recent_analyses(limit=10):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT a.id, a.idea, a.timestamp, r.graveyard_text, r.heatmap_json
        FROM analyses a
        LEFT JOIN results r ON a.id = r.analysis_id
        ORDER BY a.id DESC
        LIMIT ?;
        """,
        (limit,)
    )
    
    rows = cursor.fetchall()
    conn.close()
    
    recent = []
    for r in rows:
        recent.append({
            "id": r[0],
            "idea": r[1],
            "timestamp": r[2],
            "summary": r[3][:100] + "..." if r[3] else "",
            "heatmap": json.loads(r[4]) if r[4] else {}
        })
    return recent

def get_analysis_by_id(analysis_id):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT a.idea, a.timestamp, s.full_scraped_text, r.heatmap_json, r.fixes_json, r.graveyard_text, r.raw_content, r.raw_combined_markdown, r.scraped_urls, r.source_count
        FROM analyses a
        LEFT JOIN raw_scrapes s ON a.id = s.analysis_id
        LEFT JOIN results r ON a.id = r.analysis_id
        WHERE a.id = ?;
        """,
        (analysis_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
        
    return {
        "idea": row[0],
        "timestamp": row[1],
        "full_scraped_text": row[2],
        "heatmap": json.loads(row[3]) if row[3] else {},
        "fixes": json.loads(row[4]) if row[4] else [],
        "graveyard": row[5],
        "raw_content": row[6],
        "raw_combined_markdown": row[7],
        "scraped_urls": json.loads(row[8]) if (row[8] is not None and row[8] != "") else [],
        "source_count": row[9]
    }
