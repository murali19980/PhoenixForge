import sqlite3
import json
from datetime import datetime

DB_PATH = "phoenixforge.db"

def get_connection():
    """Connect to SQLite database with WAL mode and timeout settings."""
    conn = sqlite3.connect(DB_PATH)
    # Enable Write-Ahead Logging (WAL) for concurrent read/write stability
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA cache_size=-64000;")  # 64MB cache
    return conn

def init_db():
    conn = get_connection()
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
        print(f"Error during results migration: {e}")

    # SAFE SCHEMA MIGRATION: check analyses table columns for strategy and score and alter if missing
    try:
        cursor.execute("PRAGMA table_info(analyses)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "strategy_metadata" not in columns:
            print("Adding strategy_metadata column to analyses table...")
            cursor.execute("ALTER TABLE analyses ADD COLUMN strategy_metadata TEXT;")
            
        if "quality_score" not in columns:
            print("Adding quality_score column to analyses table...")
            cursor.execute("ALTER TABLE analyses ADD COLUMN quality_score REAL DEFAULT 0.0;")
            
        conn.commit()
    except Exception as e:
        print(f"Error during analyses migration: {e}")
        
    conn.commit()
    conn.close()

def save_analysis(idea, full_scraped_text, heatmap_dict, fixes_list, graveyard_text, raw_content, 
                  raw_combined_markdown=None, scraped_urls=None, source_count=None, 
                  strategy_metadata=None, quality_score=0.0):
    init_db()  # Ensure database and tables exist
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        timestamp = datetime.now().isoformat()
        
        # Insert into analyses with strategy metadata and quality score
        cursor.execute(
            """
            INSERT INTO analyses (idea, timestamp, strategy_metadata, quality_score) 
            VALUES (?, ?, ?, ?);
            """,
            (
                idea, 
                timestamp, 
                json.dumps(strategy_metadata) if strategy_metadata is not None else None, 
                quality_score
            )
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
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT a.id, a.idea, a.timestamp, r.graveyard_text, r.heatmap_json, a.quality_score
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
            "heatmap": json.loads(r[4]) if r[4] else {},
            "quality_score": r[5] if r[5] is not None else 0.0
        })
    return recent

def get_analysis_by_id(analysis_id):
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """
        SELECT a.idea, a.timestamp, s.full_scraped_text, r.heatmap_json, r.fixes_json, r.graveyard_text, r.raw_content, r.raw_combined_markdown, r.scraped_urls, r.source_count, a.strategy_metadata, a.quality_score
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
        "source_count": row[9],
        "strategy_metadata": json.loads(row[10]) if (row[10] is not None and row[10] != "") else None,
        "quality_score": row[11] if row[11] is not None else 0.0
    }

def clear_all_history():
    """Clear all records from history tables."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM analyses;")
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
