import os
import sys
import json
import threading
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, HTTPException

# Reconfigure stdout/stderr to utf-8 to avoid encoding errors on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.database import get_db_connection, init_db
from backend.collector import collect_new_releases
from backend.analyzer import analyze_document, SETTINGS_PATH, load_settings

# Initialize FastAPI app
app = FastAPI(title="Korean National Indicators Dashboard")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

# Lock for collector to prevent concurrent runs
collector_lock = threading.Lock()
is_collecting = False

class SettingsModel(BaseModel):
    gemini_api_key: str

@app.on_event("startup")
def startup_event():
    """Ensure database is initialized on startup."""
    init_db()

# --- Page Router ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serve the main index.html file."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h2>Frontend files not found. Please create frontend/index.html</h2>")

@app.get("/style.css")
def read_css():
    """Serve the CSS stylesheet."""
    css_path = os.path.join(FRONTEND_DIR, "style.css")
    if os.path.exists(css_path):
        return FileResponse(css_path, media_type="text/css")
    raise HTTPException(status_code=404, detail="CSS file not found")

@app.get("/app.js")
def read_js():
    """Serve the app JavaScript file."""
    js_path = os.path.join(FRONTEND_DIR, "app.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="JavaScript file not found")

# --- API Endpoints ---

@app.get("/api/articles")
def get_articles(source: str = None, status: str = None, search: str = None):
    """Retrieve list of articles, optionally filtered."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT id, source, title, link, pub_date, fetch_date, status, summary, attachments FROM articles WHERE 1=1"
    params = []
    
    if source:
        query += " AND source = ?"
        params.append(source)
    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (title LIKE ? OR summary LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")
        
    query += " ORDER BY pub_date DESC, id DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    articles = []
    for r in rows:
        articles.append({
            "id": r["id"],
            "source": r["source"],
            "title": r["title"],
            "link": r["link"],
            "pub_date": r["pub_date"],
            "fetch_date": r["fetch_date"],
            "status": r["status"],
            "summary": r["summary"],
            "attachments": json.loads(r["attachments"]) if r["attachments"] else []
        })
        
    conn.close()
    return articles

@app.get("/api/articles/{article_id}")
def get_article_details(article_id: int):
    """Retrieve full details of a specific article."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Article not found")
        
    # Fetch indicators related to this article
    cursor.execute("SELECT indicator_key, indicator_name, value, unit, period FROM indicators WHERE article_id = ?", (article_id,))
    ind_rows = cursor.fetchall()
    indicators = [dict(ir) for ir in ind_rows]
    
    article = {
        "id": row["id"],
        "source": row["source"],
        "title": row["title"],
        "link": row["link"],
        "pub_date": row["pub_date"],
        "fetch_date": row["fetch_date"],
        "status": row["status"],
        "summary": row["summary"],
        "impact": row["impact"],
        "raw_text": row["raw_text"],
        "attachments": json.loads(row["attachments"]) if row["attachments"] else [],
        "indicators": indicators
    }
    
    conn.close()
    return article

@app.get("/api/download")
def download_file(path: str):
    """Serve local downloaded files to the frontend."""
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    # Return as an attachment so browser downloads it
    return FileResponse(path, filename=os.path.basename(path))

@app.delete("/api/articles/{article_id}")
def delete_article(article_id: int):
    """Delete article from database and its downloaded files."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT attachments FROM articles WHERE id = ?", (article_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Article not found")
        
    # Delete files
    if row["attachments"]:
        try:
            attachments = json.loads(row["attachments"])
            for att in attachments:
                path = att.get("local_path")
                if path and os.path.exists(path):
                    os.remove(path)
        except Exception as e:
            print("Error deleting files:", e)
            
    cursor.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()
    return {"message": f"Article {article_id} deleted successfully."}

def run_collector_and_analyzer():
    """Background task to run scraper and analyze new documents."""
    global is_collecting
    if not collector_lock.acquire(blocking=False):
        print("Collector already running.")
        return
        
    is_collecting = True
    try:
        print("Starting background collection...")
        new_ids = collect_new_releases()
        print(f"Collected {len(new_ids)} new releases. Beginning analysis...")
        
        for art_id in new_ids:
            try:
                analyze_document(art_id)
            except Exception as e:
                print(f"Failed to analyze article {art_id}: {e}")
                
        # Also re-analyze any articles that are still marked 'pending'
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM articles WHERE status = 'pending'")
        pending_rows = cursor.fetchall()
        conn.close()
        
        for r in pending_rows:
            try:
                analyze_document(r["id"])
            except Exception as e:
                print(f"Failed to analyze pending article {r['id']}: {e}")
                
    finally:
        is_collecting = False
        collector_lock.release()
        print("Background collection and analysis finished.")

@app.post("/api/collect")
def trigger_collection(background_tasks: BackgroundTasks):
    """Trigger collection of new press releases in the background."""
    global is_collecting
    if is_collecting:
        return {"status": "running", "message": "Collection is already in progress."}
        
    background_tasks.add_task(run_collector_and_analyzer)
    return {"status": "started", "message": "Collection and analysis started in the background."}

@app.get("/api/collect/status")
def get_collection_status():
    """Check if the scraper is currently running."""
    global is_collecting
    return {"is_collecting": is_collecting}

@app.post("/api/analyze/{article_id}")
def trigger_analysis(article_id: int):
    """Manually trigger AI analysis for a specific article."""
    success = analyze_document(article_id)
    if not success:
        raise HTTPException(status_code=500, detail="Analysis failed. Check logs for details.")
    return {"status": "success", "message": f"Article {article_id} analyzed successfully."}

@app.get("/api/indicators")
def get_indicators(key: str = None):
    """Retrieve historical indicator values for charting."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT i.indicator_key, i.indicator_name, i.value, i.unit, i.period, a.title, a.link, a.pub_date
        FROM indicators i
        LEFT JOIN articles a ON i.article_id = a.id
    """
    params = []
    
    if key:
        query += " WHERE i.indicator_key = ?"
        params.append(key)
        
    query += " ORDER BY i.period ASC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    data = []
    for r in rows:
        data.append(dict(r))
    return data

@app.get("/api/settings")
def get_settings():
    """Retrieve current settings."""
    settings = load_settings()
    # Mask API key for security
    api_key = settings.get("gemini_api_key", "")
    masked_key = ""
    if api_key:
        masked_key = api_key[:6] + "*" * (len(api_key) - 10) + api_key[-4:] if len(api_key) > 10 else "****"
    
    return {
        "gemini_api_key_configured": bool(api_key),
        "gemini_api_key_masked": masked_key
    }

@app.post("/api/settings")
def save_new_settings(payload: SettingsModel):
    """Save new settings."""
    settings = {}
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except Exception:
            pass
            
    # Update API key
    new_key = payload.gemini_api_key.strip()
    # If the user sends a masked key (e.g. contains '*'), do not overwrite if we already have it
    if "*" in new_key and settings.get("gemini_api_key"):
        pass
    else:
        settings["gemini_api_key"] = new_key
        
    try:
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return {"status": "success", "message": "Settings saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, reload=True)
