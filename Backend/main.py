import sys
import asyncio

# Windows-specific fix for Playwright/Subprocesses
# MUST BE AT THE VERY TOP
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

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
            
        # 1. LinkedIn Job Search (Agent scrapes first)
        from agents.Linkedin_agent import search_linkedin_jobs
        linkedin_jobs_raw = await search_linkedin_jobs(result)

        
        # 2. Evaluate LinkedIn jobs (AI matches it)
        from agents.ai_matcher import match_linkedin_jobs
        top_linkedin_jobs = match_linkedin_jobs(user_id, result)

        # 3. Automatically scrape generic jobs based on the parsed resume data
        jobs = scrape_all_jobs(result)
        top_jobs = match_jobs(user_id, result)
        
        # # 4. Spin up localized scraping for target city
        # from agents.local_city_job_scraper import find_local_jobs
        # local_jobs_raw = find_local_jobs(result)
        
        # # 5. Iteratively evaluate localized jobs specifically against profile
        # from agents.ai_matcher import match_local_jobs
        # top_local_jobs = match_local_jobs(user_id, result)
        
        # # 6. Spin up MNC career page scraping
        # from agents.career_scraper import fetch_mnc_jobs
        # mnc_jobs_raw = await fetch_mnc_jobs(result)
        
        # # 7. Evaluate MNC jobs
        # from agents.ai_matcher import match_mnc_jobs
        # top_mnc_jobs = match_mnc_jobs(user_id, result)
        
        return {
            "message": "Jobs scraped and AI dynamically matched successfully",
            "data": result,
            "jobs_scraped_amount": len(jobs) + len(linkedin_jobs_raw),
            "top_matched_jobs": top_jobs,
            # "top_local_jobs": top_local_jobs,
            # "top_mnc_jobs": top_mnc_jobs,
            "top_linkedin_jobs": top_linkedin_jobs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/find-contacts", status_code=status.HTTP_200_OK)
async def find_contacts(job: Dict[str, Any] = Body(...)):
    """Finds HR contacts and employees for a specific job."""
    try:
        from agents.contact_finder import find_contacts_for_job
        contacts_data = find_contacts_for_job(job)
        return contacts_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

