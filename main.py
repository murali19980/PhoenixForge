from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, validator
import subprocess
import os
import json
import re
import uuid
import asyncio
import logging
import shutil
from datetime import datetime
from typing import Optional

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Global standard logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('phoenixforge.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("phoenixforge")

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="PhoenixForge 🔥")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Global dict to store background task progress
active_tasks = {}

class IdeaRequest(BaseModel):
    idea: str = Field(..., min_length=3, max_length=150)
    
    @validator('idea')
    def validate_idea(cls, v: str) -> str:
        # Allowed character set: letters, numbers, spaces, basic punctuation
        allowed = re.compile(r'^[a-zA-Z0-9\s\-_,\.!?\'"()]+$')
        if not allowed.match(v):
            raise ValueError(
                'Invalid characters. Only letters, numbers, spaces, '
                'and basic punctuation (!?.,-\'"()) are allowed.'
            )
        # Block obvious injection/scripting patterns
        blocked = {'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'EXEC', 
                  'UNION', 'ALTER', 'CREATE', 'SCRIPT', 'ALERT', 'ONLOAD'}
        if any(kw in v.upper() for kw in blocked):
            raise ValueError('Input contains forbidden keywords or patterns.')
        return v.strip()

def extract_pipeline_metadata(content):
    pipeline = {"gathered": "N/A", "cleaned": "N/A", "organized": "N/A", "presented": "N/A"}
    pipeline_match = re.search(r'## Pipeline Metadata\s*```json\s*([\s\S]*?)```', content)
    if not pipeline_match:
        pipeline_match = re.search(r'## Pipeline Metadata\s*([\s\S]*?)(?=\n##|$)', content)
    if pipeline_match:
        try:
            pipeline = json.loads(pipeline_match.group(1).strip())
        except:
            pass
    return pipeline

async def run_pipeline_worker(task_id: str, idea: str):
    import engine
    import coordinator
    try:
        # Consult coordinator to get top performing strategies
        best_strats = coordinator.get_best_strategies(limit=3)
        
        # Generate optimized queries based on past performance
        queries, templates = coordinator.generate_optimized_queries(idea, best_strats)
        
        strategy_metadata = {
            "query_templates": templates,
            "queries_used": queries,
            "scraper_type": "crawl4ai_BS4_fallback",
            "prompt_version": 1
        }
        
        # Run the CPU-heavy scraping & LLM pipeline in a separate thread pool
        # to keep the FastAPI main event loop free for status polling.
        payload = await asyncio.to_thread(
            engine.run_phoenixforge,
            idea,
            task_id,
            active_tasks,
            queries,
            strategy_metadata
        )
        active_tasks[task_id]["status"] = "completed"
        active_tasks[task_id]["current_step"] = "Completed"
        active_tasks[task_id]["message"] = "Analysis report generated successfully."
        active_tasks[task_id]["results"] = payload
    except Exception as e:
        logger.error("Pipeline worker failed:", exc_info=True)
        active_tasks[task_id]["status"] = "failed"
        active_tasks[task_id]["current_step"] = "Analysis failed"
        active_tasks[task_id]["message"] = str(e)

@app.post("/api/analyze")
@limiter.limit("3/minute")
async def analyze_risk(request: Request, idea_req: IdeaRequest):
    if not idea_req.idea:
        raise HTTPException(status_code=400, detail="Idea cannot be empty")
    
    # Enforce concurrency limit of 2 tasks per client IP
    client_ip = request.client.host
    running_tasks = sum(
        1 for t in active_tasks.values() 
        if t.get("client_ip") == client_ip and t.get("status") == "processing"
    )
    if running_tasks >= 2:
        raise HTTPException(status_code=429, detail="Too many concurrent analyses from this IP. Please wait for them to finish.")
    
    task_id = str(uuid.uuid4())
    active_tasks[task_id] = {
        "status": "processing",
        "current_step": "Initializing search queries...",
        "extracted_count": 0,
        "total_articles": 0,
        "message": "Starting research agent...",
        "results": None,
        "client_ip": client_ip
    }
    
    # Schedule task concurrently on the event loop
    asyncio.create_task(run_pipeline_worker(task_id, idea_req.idea))
    
    return {"task_id": task_id}

@app.get("/api/status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in active_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return active_tasks[task_id]

@app.get("/api/coordinator/status")
async def get_coordinator_status():
    try:
        import coordinator
        summary = coordinator.summarize_learning()
        best = coordinator.get_best_strategies(limit=1)
        best_score = best[0].get("quality_score", 0.0) if best else 0.0
        return {
            "status": "success",
            "summary": summary,
            "best_score": best_score
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/history/clear")
async def clear_history():
    try:
        import history
        history.clear_all_history()
        return {"status": "success", "message": "History cleared successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def render_mermaid_to_image(mermaid_code):
    import base64
    import urllib.parse
    import requests
    import tempfile
    import os
    
    encoded = urllib.parse.quote(mermaid_code)
    
    # Strategy 1: Try mermaid.ink PNG (online, highly compatible)
    try:
        url = f"https://mermaid.ink/img/{encoded}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8'), "png"
    except Exception as e:
        print(f"mermaid.ink img failed: {e}")
        
    # Strategy 1b: Try mermaid.ink SVG
    try:
        url = f"https://mermaid.ink/svg/{encoded}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8'), "svg"
    except Exception as e:
        print(f"mermaid.ink svg failed: {e}")
        
    # Strategy 2: Try local Mermaid CLI (mmdc) to render to SVG
    input_path = None
    output_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', encoding='utf-8', delete=False) as f:
            f.write(mermaid_code)
            input_path = f.name
        output_path = input_path + ".svg"
        
        # Try global mmdc first
        try:
            mmdc_path = shutil.which("mmdc") or "mmdc"
            subprocess.run(
                [mmdc_path, '-i', input_path, '-o', output_path, '-b', 'transparent'],
                check=True,
                timeout=10,
                capture_output=True
            )
        except Exception as cli_err:
            logger.warning(f"Direct mmdc failed, trying npx: {cli_err}")
            # Try via npx
            npx_path = shutil.which("npx") or "npx"
            subprocess.run(
                [npx_path, '--yes', '@mermaid-js/mermaid-cli', 'mmdc', '-i', input_path, '-o', output_path, '-b', 'transparent'],
                check=True,
                timeout=15,
                capture_output=True
            )
            
        with open(output_path, 'rb') as f:
            svg_data = f.read()
            
        return base64.b64encode(svg_data).decode('utf-8'), "svg"
    except Exception as e:
        logger.error(f"Local Mermaid CLI failed: {e}")
    finally:
        if input_path and os.path.exists(input_path):
            try: os.unlink(input_path)
            except: pass
        if output_path and os.path.exists(output_path):
            try: os.unlink(output_path)
            except: pass
        
    # Strategy 3: Fallback placeholder (a clean text box SVG)
    placeholder_svg = f'''
    <svg width="400" height="100" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#f8f9fa" rx="8" />
      <text x="50%" y="45%" font-family="Arial" font-size="16" fill="#6c757d" text-anchor="middle">
        📊 Flowchart rendering unavailable
      </text>
      <text x="50%" y="65%" font-family="Arial" font-size="12" fill="#adb5bd" text-anchor="middle">
        Please view the live dashboard at http://127.0.0.1:8000
      </text>
    </svg>
    '''
    return base64.b64encode(placeholder_svg.encode('utf-8')).decode('utf-8'), "svg"

@app.get("/api/export/charter/pdf")
async def export_charter_pdf(id: Optional[int] = None):
    """Export Project Charter as PDF."""
    return await export_document("charter", "pdf", id)

@app.get("/api/export/charter/word")
async def export_charter_word(id: Optional[int] = None):
    """Export Project Charter as Word document."""
    return await export_document("charter", "word", id)

@app.get("/api/export/plan/pdf")
async def export_plan_pdf(id: Optional[int] = None):
    """Export Project Management Plan as PDF."""
    return await export_document("plan", "pdf", id)

@app.get("/api/export/plan/word")
async def export_plan_word(id: Optional[int] = None):
    """Export Project Management Plan as Word document."""
    return await export_document("plan", "word", id)

@app.get("/api/export/complete/pdf")
async def export_complete_pdf(id: Optional[int] = None):
    """Export Complete Report as PDF."""
    return await export_document("complete", "pdf", id)

@app.get("/api/export/complete/word")
async def export_complete_word(id: Optional[int] = None):
    """Export Complete Report as Word document."""
    return await export_document("complete", "word", id)

async def export_document(doc_type: str, format: str, id: Optional[int] = None):
    """Generic document export handler generating files completely in memory."""
    try:
        import history
        import documents
        
        # 1. Fetch analysis details from SQLite
        if id is not None:
            db_data = history.get_analysis_by_id(id)
        else:
            recent = history.get_recent_analyses(limit=1)
            if not recent:
                raise HTTPException(status_code=404, detail="No report found. Please run analysis first.")
            db_data = history.get_analysis_by_id(recent[0]["id"])
            
        if not db_data:
            raise HTTPException(status_code=404, detail="Report details not found.")
            
        # 2. Extract structured analysis data
        data = documents.extract_analysis_data(
            raw_content=db_data["raw_content"],
            heatmap=db_data["heatmap"],
            fixes=db_data["fixes"],
            graveyard=db_data["graveyard"],
            idea=db_data["idea"]
        )
        
        # 3. Generate document (docx or PDF bytes) in memory
        content = documents.generate_document(data, doc_type, format)
        
        filename = f"phoenixforge_{doc_type}_{data['idea'][:30].strip().replace(' ', '_')}.{format}"
        if format == 'pdf':
            media_type = 'application/pdf'
        else:
            media_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to export {doc_type} as {format}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed. Please check server logs.")

@app.get("/api/history")
async def get_history():
    try:
        import history
        recent = history.get_recent_analyses(limit=10)
        return {"status": "success", "history": recent}
    except Exception as e:
        logger.error(f"Failed to retrieve history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve history list.")

@app.get("/api/history/{id}")
async def get_history_by_id(id: int):
    try:
        import history
        data = history.get_analysis_by_id(id)
        if not data:
            raise HTTPException(status_code=404, detail="History entry not found")
        return {
            "status": "success",
            "heatmap": data["heatmap"],
            "fixes": data["fixes"],
            "graveyard": data["graveyard"],
            "pipeline": extract_pipeline_metadata(data["raw_content"]),
            "raw_content": data["raw_content"],
            "raw_combined_markdown": data.get("raw_combined_markdown", ""),
            "scraped_urls": data.get("scraped_urls", []),
            "source_count": data.get("source_count", 0)
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Failed to retrieve history detail for ID {id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve history entry.")

# Mount static files to serve the frontend (must be defined after endpoints)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
