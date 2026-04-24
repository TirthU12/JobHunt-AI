import httpx
import uuid
import json
from db.connection import get_db_connection

# Curated List of Tech/Product/Fintech/IT Giants
LEVER_COMPANIES = [
    {"name": "Lenskart",       "slug": "lenskart"},
    {"name": "Nykaa",          "slug": "nykaa"},
    {"name": "Dunzo",          "slug": "dunzo"},
    {"name": "Slice",          "slug": "sliceit"},
    {"name": "Jupiter",        "slug": "jupiter"},
    {"name": "FamPay",         "slug": "fampay"},
    {"name": "Cashfree",       "slug": "cashfree"},
]
GREENHOUSE_COMPANIES = [
    {"name": "Swiggy",        "token": "swiggy"},
    {"name": "Razorpay",      "token": "razorpay"},
    {"name": "Meesho",        "token": "meesho"},
    {"name": "CRED",          "token": "cred"},
    {"name": "Groww",         "token": "groww"},
    {"name": "Zepto",         "token": "zepto"},
    {"name": "PhonePe",       "token": "phonepe"},
    {"name": "Browserstack",  "token": "browserstack"},
    {"name": "Postman",       "token": "postman"},
    {"name": "Freshworks",    "token": "freshworks"},
    {"name": "Chargebee",     "token": "chargebee"},
    {"name": "Hasura",        "token": "hasura"},
    {"name": "Setu",          "token": "setu"},
]

def scrape_lever_jobs(company: str) -> list:
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    jobs = []
    try:
        response = httpx.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for job in data:
                location = job.get("categories", {}).get("location", "")
                if "India" in location or "Remote" in location or "Bengaluru" in location or "Mumbai" in location or "Delhi" in location:
                    jobs.append({
                        "title": job.get("text", ""),
                        "company": company.capitalize(),
                        "location": location,
                        "url": job.get("hostedUrl", ""),
                        "description": job.get("descriptionPlain", str(job.get("description", "")))[:5000],
                        "job_type": job.get("categories", {}).get("commitment", ""),
                        "source": "lever"
                    })
    except Exception as e:
        print(f"Lever error for {company}: {e}")
    return jobs

def scrape_greenhouse_jobs(company: str) -> list:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
    jobs = []
    try:
        response = httpx.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for job in data.get("jobs", []):
                location = job.get("location", {}).get("name", "")
                if "India" in location or "Remote" in location or "Bengaluru" in location or "Mumbai" in location or "Delhi" in location:
                    jobs.append({
                        "title": job.get("title", ""),
                        "company": company.capitalize(),
                        "location": location,
                        "url": job.get("absolute_url", ""),
                        "description": "",  # Greenhouse often requires a secondary fetch, keeping clean for now
                        "job_type": "",
                        "source": "greenhouse"
                    })
    except Exception as e:
        print(f"Greenhouse error for {company}: {e}")
    return jobs

def save_mnc_jobs_to_db(jobs: list):
    db = get_db_connection()
    if not db: return 0
    cur = db.cursor()
    saved = 0
    try:
        # Create table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mnc_jobs (
                id VARCHAR(255) PRIMARY KEY,
                title VARCHAR(500),
                company VARCHAR(255),
                location VARCHAR(255),
                source VARCHAR(100),
                url VARCHAR(1000) UNIQUE,
                description TEXT,
                job_type VARCHAR(100)
            )
        """)
        for job in jobs:
            try:
                cur.execute("""
                    INSERT INTO mnc_jobs (id, title, company, location, source, url, description, job_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
                """, (
                    str(uuid.uuid4()),
                    job.get("title", "")[:500],
                    job.get("company", "")[:255],
                    job.get("location", "")[:255],
                    job.get("source", "")[:100],
                    job.get("url", "")[:1000],
                    job.get("description", "")[:5000],
                    job.get("job_type", "")[:100]
                ))
                if cur.rowcount > 0:
                    saved += 1
            except Exception as e:
                continue
        db.commit()
    finally:
        cur.close()
        db.close()
    return saved


def scrape_all_mnc_jobs(parsed_resume: dict = None) -> list:
    print(f"\n{'='*55}")
    print(f"🏢 MNC Scraper Agent Started (Lever + Greenhouse)")
    print(f"{'='*55}")
    
    all_mnc_jobs = []
    
    for comp in LEVER_COMPANIES:
        all_mnc_jobs.extend(scrape_lever_jobs(comp))
        
    for comp in GREENHOUSE_COMPANIES:
        all_mnc_jobs.extend(scrape_greenhouse_jobs(comp))
        
    print(f"✅ Found {len(all_mnc_jobs)} MNC jobs (India + Remote)!")
    
    saved = save_mnc_jobs_to_db(all_mnc_jobs)
    print(f"💾 Saved {saved} new MNC jobs to DB.")
    
    return all_mnc_jobs
