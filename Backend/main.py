from fastapi import FastAPI, UploadFile, File, HTTPException, status, Body
from typing import Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import shutil

from agents.resume_parser import process_resume
from agents.job_scraper import scrape_all_jobs
from agents.ai_matcher import match_jobs

load_dotenv()

app= FastAPI(
    title="Jobhunt",
    description="Ai Powered Jobhunt website",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return{
        "message": "Welcome to Jobhunt API"
    }

@app.get("/health")
def health():
    from db.connection import get_db_connection
    conn = get_db_connection()
    if conn:
        conn.close()
        return{
            "status": "ok"
        }
    else:
        return{
            "status": "error"
        }

@app.post("/parse-resume", status_code=status.HTTP_200_OK)
async def parse_resume(resume: UploadFile = File(...)):
    """Only parses the resume and returns the JSON payload for frontend editing."""
    if not resume.filename.endswith(('.pdf', '.docx')):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported.")
        
    os.makedirs("temp", exist_ok=True)
    file_path = f"temp/{resume.filename}"
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(resume.file, buffer)
            
        result = process_resume(file_path)
        
        if not result or not result.get("user_id"):
            raise HTTPException(status_code=400, detail="Could not process resume or no email was found.")
            
        return {
            "message": "Resume parsed successfully. Please edit if needed.",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@app.post("/search-jobs", status_code=status.HTTP_200_OK)
async def search_jobs(payload: Dict[str, Any] = Body(...)):
    """Receives edited profile data and runs the heavy scraping + LLM scoring."""
    try:
        result = payload
        user_id = result.get("user_id")
        if not user_id:
            raise HTTPException(status_code=400, detail="Payload missing user_id.")
            
        # 1. Automatically scrape jobs based on the parsed resume data!
        jobs = scrape_all_jobs(result)
        
        # 2. Use AI Matcher to score and pick the top 10 recommended jobs
        top_jobs = match_jobs(user_id, result)
        
        # 3. Spin up localized scraping for target city
        from agents.local_city_job_scraper import find_local_jobs
        local_jobs_raw = find_local_jobs(result)
        
        # 4. Iteratively evaluate localized jobs specifically against profile
        from agents.ai_matcher import match_local_jobs
        top_local_jobs = match_local_jobs(user_id, result)
        
        return {
            "message": "Jobs scraped and AI dynamically matched successfully",
            "data": result,
            "jobs_scraped_amount": len(jobs),
            "top_matched_jobs": top_jobs,
            "top_local_jobs": top_local_jobs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
