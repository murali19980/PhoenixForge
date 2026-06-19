import sqlite3
import json

DB_PATH = "phoenixforge.db"

def get_best_strategies(limit=3):
    """Query the SQLite database for the top performing analyses based on quality_score."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column exists first (to prevent crash before migration runs)
        cursor.execute("PRAGMA table_info(analyses)")
        columns = [row[1] for row in cursor.fetchall()]
        if "quality_score" not in columns or "strategy_metadata" not in columns:
            return []
            
        cursor.execute(
            """
            SELECT idea, strategy_metadata, quality_score 
            FROM analyses 
            WHERE quality_score IS NOT NULL AND strategy_metadata IS NOT NULL
            ORDER BY quality_score DESC 
            LIMIT ?;
            """,
            (limit,)
        )
        rows = cursor.fetchall()
        
        strategies = []
        for r in rows:
            try:
                metadata = json.loads(r[1])
                strategies.append({
                    "idea": r[0],
                    "metadata": metadata,
                    "quality_score": r[2]
                })
            except Exception as parse_err:
                print(f"[Coordinator] Error parsing strategy JSON: {parse_err}")
                
        return strategies
    except Exception as e:
        print(f"[Coordinator] Failed to query best strategies: {e}")
        return []
    finally:
        conn.close()

def generate_optimized_queries(idea, top_strategies):
    """Adapt search queries using high-scoring query patterns from past runs."""
    default_templates = [
        "{idea} failure post mortem",
        "{idea} horror story",
        "{idea} shut down",
        "{idea} abandoned"
    ]
    
    if not top_strategies:
        print("[Coordinator] No past strategies found. Using default query templates.")
        return [t.replace("{idea}", idea) for t in default_templates], default_templates
        
    # Aggregate templates used in top strategies, weighted by quality score
    template_scores = {}
    for strat in top_strategies:
        score = strat.get("quality_score", 0.0)
        metadata = strat.get("metadata", {})
        templates = metadata.get("query_templates") or []
        
        # Fallback in case templates wasn't logged but queries was
        if not templates and "queries_used" in metadata:
            past_idea = strat.get("idea", "")
            templates = [q.replace(past_idea, "{idea}") for q in metadata["queries_used"]]
            
        for t in templates:
            template_scores[t] = template_scores.get(t, 0.0) + score
            
    # Sort templates by score descending
    sorted_templates = sorted(template_scores.items(), key=lambda x: x[1], reverse=True)
    selected_templates = [item[0] for item in sorted_templates[:4]]
    
    # If we got fewer than 4 templates, pad with default ones
    for t in default_templates:
        if len(selected_templates) >= 4:
            break
        if t not in selected_templates:
            selected_templates.append(t)
            
    print(f"[Coordinator] Generated optimized query templates based on past wins: {selected_templates}")
    return [t.replace("{idea}", idea) for t in selected_templates], selected_templates

def summarize_learning():
    """Returns a string summary of the best strategy and historical progress."""
    top = get_best_strategies(limit=1)
    if not top:
        return "PhoenixForge is in bootstrap mode. Scrapers are gathering initial failure signals..."
        
    best = top[0]
    score = best.get("quality_score", 0.0)
    metadata = best.get("metadata", {})
    queries = metadata.get("query_templates") or ["{idea} failure post mortem"]
    scraper = metadata.get("scraper_type") or "Crawl4AI"
    
    return f"Best Strategy: DDG/Google + templates {queries[:2]} + scraper '{scraper}' (Highest quality score: {score:.2f})"
