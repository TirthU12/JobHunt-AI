import os
import json
import uuid
import asyncio
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from jobspy import scrape_jobs
from duckduckgo_search import DDGS
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

load_dotenv()

# ─── LangChain LLM ───────────────────────────────────────────────────────────
llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model="openai/gpt-oss-120",
    temperature=0
)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — SCRAPE GLOBAL JOB BOARDS (LinkedIn, Indeed, Glassdoor)
# ══════════════════════════════════════════════════════════════════════════════

def scrape_global_jobs(job_title: str, location: str,
                       results_wanted: int = 30) -> list:
    """
    Scrape jobs from LinkedIn, Indeed, Glassdoor using JobSpy.
    All free — no API key needed.
    """
    print(f"\n🌍 Scraping global job boards...")
    print(f"   Title    : {job_title}")
    print(f"   Location : {location}")

    all_jobs = []

    # ── Board 1: LinkedIn + Indeed + Glassdoor ──────────────────────────────
    try:
        jobs_df = scrape_jobs(
            site_name=["linkedin", "indeed", "glassdoor", "zip_recruiter","naukri","angel_co","monster","simplyhired","dice","careerjet","careerbuilder","caree"],
            search_term=job_title,
            location=location,
            results_wanted=results_wanted,
            country_indeed="India",
            linkedin_fetch_description=True,
            hours_old=72          # only jobs posted in last 72 hours
        )

        if jobs_df is not None and not jobs_df.empty:
            for _, row in jobs_df.iterrows():
                job = {
                    "title"      : str(row.get("title", "")).strip(),
                    "company"    : str(row.get("company", "")).strip(),
                    "location"   : str(row.get("location", "")).strip(),
                    "source"     : str(row.get("site", "")).strip(),
                    "url"        : str(row.get("job_url", "")).strip(),
                    "description": str(row.get("description", ""))[:5000],
                    "salary"     : str(row.get("min_amount", "")) + " - " +
                                   str(row.get("max_amount", "")),
                    "job_type"   : str(row.get("job_type", "")).strip(),
                    "posted_at"  : str(row.get("date_posted", "")).strip(),
                    "raw_data"   : {}
                }
                if job["title"] and job["url"]:
                    all_jobs.append(job)

            print(f"   ✅ JobSpy found: {len(all_jobs)} jobs")

    except Exception as e:
        print(f"   ⚠️  JobSpy error: {e}")

    return all_jobs


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — SCRAPE LOCAL JOBS (India-specific boards)
# ══════════════════════════════════════════════════════════════════════════════

def scrape_local_jobs_india(job_title: str, location: str) -> list:
    """
    Scrape India-specific job boards using Serper / SearchApi (Google Search APIs).
    Covers Naukri, Internshala, Shine, TimesJobs.
    """
    import httpx
    import os
    print(f"\n🇮🇳 Scraping India job boards with Serper/Search APIs...")
    print(f"   Title    : {job_title}")
    print(f"   Location : {location}")

    all_jobs = []
    # Remove tight quotes to permit fuzzy matching for better results
    indian_boards = [
        f'site:naukri.com {job_title} {location}',
        f'site:internshala.com {job_title} {location}',
        f'site:shine.com {job_title} {location}',
        f'site:timesjobs.com {job_title} {location}',
        f'site:foundit.in {job_title} {location}',
    ]

    serper_api_key = os.getenv("SERPER_API_KEY")
    search_api_key = os.getenv("SEARCH_API_KEY")
    
    for query in indian_boards:
        try:
            board_name = query.split("site:")[1].split(" ")[0]
            results = []
            
            if serper_api_key:
                # Use Serper API
                url = "https://google.serper.dev/search"
                payload = json.dumps({"q": query, "num": 20})
                headers = {
                    'X-API-KEY': serper_api_key,
                    'Content-Type': 'application/json'
                }
                response = httpx.post(url, headers=headers, data=payload, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    for r in data.get("organic", []):
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("link", ""),
                            "snippet": r.get("snippet", "")
                        })
            elif search_api_key:
                # Use SearchApi.io as an alternative when SEARCH_API_KEY is provided
                url = f"https://www.searchapi.io/api/v1/search?engine=google&q={query}&api_key={search_api_key}&num=20"
                response = httpx.get(url, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    for r in data.get("organic_results", []):
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("link", ""),
                            "snippet": r.get("snippet", "")
                        })
            else:
                # Fallback to DDGS if keys are missing
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    for r in ddgs.text(query, max_results=20):
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("href", ""),
                            "snippet": r.get("body", "")
                        })

            for r in results:
                job = {
                    "title"      : r.get("title", "").strip(),
                    "company"    : "",
                    "location"   : location,
                    "source"     : board_name,
                    "url"        : r.get("url", "").strip(),
                    "description": r.get("snippet", "").strip()[:2000],
                    "salary"     : "",
                    "job_type"   : "",
                    "posted_at"  : "",
                    "raw_data"   : {}
                }
                if job["title"] and job["url"]:
                    all_jobs.append(job)

        except Exception as e:
            print(f"   ⚠️  Error scraping {query[:30]}: {e}")

    print(f"   ✅ India boards found: {len(all_jobs)} jobs")
    return all_jobs


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — SCRAPE FREE REMOTE JOB APIs (no API key needed)
# ══════════════════════════════════════════════════════════════════════════════

def scrape_remote_jobs(job_title: str) -> list:
    """
    Fetch from free public job APIs — no key required.
    Covers RemoteOK, Jobicy, Arbeitnow.
    """
    import httpx
    import urllib.parse

    print(f"\n🌐 Scraping remote job APIs...")
    all_jobs = []
    
    # We use the first word of the title (e.g., 'web' or 'python') or the main skill to search the tags
    main_skill = job_title.split()[0].lower() if job_title else "developer"

    # ── RemoteOK (free public API) ───────────────────────────────────────────
    try:
        res = httpx.get(
            "https://remoteok.com/api",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        data = res.json()
        keyword = job_title.lower()

        for item in data[1:]:  # first item is metadata
            title = item.get("position", "").lower()
            if any(word in title for word in keyword.split()):
                all_jobs.append({
                    "title"      : item.get("position", ""),
                    "company"    : item.get("company", ""),
                    "location"   : "Remote",
                    "source"     : "remoteok",
                    "url"        : item.get("url", ""),
                    "description": item.get("description", "")[:3000],
                    "salary"     : item.get("salary", ""),
                    "job_type"   : "remote",
                    "posted_at"  : item.get("date", ""),
                    "raw_data"   : {}
                })

        print(f"   ✅ RemoteOK: {len(all_jobs)} jobs")

    except Exception as e:
        print(f"   ⚠️  RemoteOK error: {e}")

    # ── Jobicy (free public API) ─────────────────────────────────────────────
    try:
        encoded_tag = urllib.parse.quote_plus(main_skill)
        res = httpx.get(
            f"https://jobicy.com/api/v2/remote-jobs?count=30&tag={encoded_tag}",
            timeout=15
        )
        data = res.json()
        before = len(all_jobs)

        for item in data.get("jobs", []):
            all_jobs.append({
                "title"      : item.get("jobTitle", ""),
                "company"    : item.get("companyName", ""),
                "location"   : "Remote",
                "source"     : "jobicy",
                "url"        : item.get("url", ""),
                "description": item.get("jobDescription", "")[:3000],
                "salary"     : item.get("annualSalaryMax", ""),
                "job_type"   : "remote",
                "posted_at"  : item.get("pubDate", ""),
                "raw_data"   : {}
            })

        print(f"   ✅ Jobicy: {len(all_jobs) - before} jobs")

    except Exception as e:
        print(f"   ⚠️  Jobicy error: {e}")

    return all_jobs


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — CLEAN + DEDUPLICATE JOBS WITH LangChain
# ══════════════════════════════════════════════════════════════════════════════

def clean_job_title(title: str) -> str:
    """Remove noise from job titles."""
    noise = ["urgent", "hiring", "immediately", "apply now",
             "openings", "vacancy", "walk-in", "fresher"]
    title_lower = title.lower()
    for word in noise:
        title_lower = title_lower.replace(word, "").strip()
    return title.strip()


def deduplicate_jobs(jobs: list) -> list:
    """Remove duplicate jobs by URL."""
    seen_urls = set()
    unique_jobs = []

    for job in jobs:
        url = job.get("url", "").strip()
        if url and url not in seen_urls:
            seen_urls.add(url)
            job["title"] = clean_job_title(job.get("title", ""))
            unique_jobs.append(job)

    print(f"\n🧹 Deduplication: {len(jobs)} → {len(unique_jobs)} unique jobs")
    return unique_jobs


def enrich_job_with_ai(job: dict, user_skills: list) -> dict:
    """
    Use LangChain + Groq to extract missing fields from job description.
    Only runs if description is available and fields are missing.
    """
    if not job.get("description") or len(job["description"]) < 100:
        return job

    if job.get("company") and job.get("salary"):
        return job  # already has enough data

    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a job data extractor. Return ONLY valid JSON."),
        ("human", """Extract from this job description:
        {{
          "company": "company name if not obvious",
          "salary": "salary range if mentioned",
          "required_skills": ["list", "of", "skills"],
          "experience_required": "e.g. 2-4 years",
          "job_type": "full-time/part-time/contract/remote"
        }}

        Job Title: {title}
        Description: {description}

        Return ONLY JSON.
        """)
    ])

    chain = prompt | llm | parser

    try:
        enriched = chain.invoke({
            "title": job.get("title", ""),
            "description": job.get("description", "")[:2000]
        })

        if not job.get("company") and enriched.get("company"):
            job["company"] = enriched["company"]
        if not job.get("salary") and enriched.get("salary"):
            job["salary"] = enriched["salary"]
        job["required_skills"] = enriched.get("required_skills", [])
        job["experience_required"] = enriched.get("experience_required", "")

    except Exception:
        pass  # enrichment is optional

    return job


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — SAVE JOBS TO POSTGRESQL
# ══════════════════════════════════════════════════════════════════════════════

def save_jobs_to_db(jobs: list) -> int:
    """Save all jobs to PostgreSQL. Returns count of newly saved jobs."""
    from db.connection import get_db_connection

    db = get_db_connection()
    cur = db.cursor()
    saved_count = 0

    try:
        for job in jobs:
            try:
                cur.execute(
                    """INSERT INTO jobs
                       (id, title, company, location, source,
                        url, description, salary, job_type, raw_data)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (url) DO NOTHING""",
                    (
                        str(uuid.uuid4()),
                        job.get("title", "")[:500],
                        job.get("company", "")[:255],
                        job.get("location", "")[:255],
                        job.get("source", "")[:100],
                        job.get("url", "")[:1000],
                        job.get("description", "")[:5000],
                        job.get("salary", "")[:255],
                        job.get("job_type", "")[:100],
                        json.dumps({
                            "required_skills"    : job.get("required_skills", []),
                            "experience_required": job.get("experience_required", ""),
                            "posted_at"          : job.get("posted_at", "")
                        })
                    )
                )
                if cur.rowcount > 0:
                    saved_count += 1

            except Exception as e:
                print(f"   ⚠️  Skip job '{job.get('title', '')}': {e}")
                continue

        db.commit()
        print(f"   ✅ Saved {saved_count} new jobs to DB")

    except Exception as e:
        db.rollback()
        print(f"❌ DB error: {e}")
        raise e

    finally:
        cur.close()
        db.close()

    return saved_count


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — GET JOBS FROM DB FOR A USER
# ══════════════════════════════════════════════════════════════════════════════

def get_jobs_from_db(limit: int = 50) -> list:
    """Fetch saved jobs from PostgreSQL."""
    from db.connection import get_db_connection

    db = get_db_connection()
    cur = db.cursor()

    try:
        cur.execute(
            """SELECT id, title, company, location, source, url,
                      description, salary, job_type, scraped_at
               FROM jobs
               ORDER BY scraped_at DESC
               LIMIT %s""",
            (limit,)
        )
        rows = cur.fetchall()
        columns = ["id", "title", "company", "location", "source",
                   "url", "description", "salary", "job_type", "scraped_at"]
        return [dict(zip(columns, row)) for row in rows]

    finally:
        cur.close()
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION — CALL THIS FROM OTHER AGENTS
# ══════════════════════════════════════════════════════════════════════════════

def scrape_all_jobs(parsed_resume: dict) -> list:
    """
    Full pipeline:
    1. Scrape global boards (LinkedIn, Indeed, Glassdoor)
    2. Scrape India boards (Naukri, Internshala etc.)
    3. Scrape remote APIs (RemoteOK, Jobicy)
    4. Deduplicate all jobs
    5. Save to DB

    Returns list of all unique jobs found.
    """
    # Collect top queries from user data
    search_queries = []
    if parsed_resume.get("search_keywords"):
        search_queries.extend(parsed_resume["search_keywords"][:2])
    if parsed_resume.get("job_titles"):
        search_queries.extend(parsed_resume["job_titles"][:2])
    
    # Deduplicate and remove empties
    search_queries = list(dict.fromkeys([q.strip() for q in search_queries if q.strip()]))
    
    if not search_queries:
        # Build title from top skills
        skills = parsed_resume.get("skills", [])
        search_queries = [f"{skills[0]} Developer" if skills else "Software Engineer"]

    # --- EXPERIENCE INJECTION ---
    # To prevent grabbing 5+ year roles for 1 year candidates, directly append constraints softly
    exp_years = parsed_resume.get("experience_years", 0)
    if exp_years <= 1:
        search_queries = [q + " Entry Level" for q in search_queries]
    elif exp_years <= 3:
        search_queries = [q + " Junior" for q in search_queries]
        
    # We refine the location by only taking the City to prevent overtight location boundaries
    raw_location = parsed_resume.get("location", "India")
    location = raw_location.split(",")[0].strip() if raw_location else "India"

    print(f"\n{'='*55}")
    print(f"🚀 Job Scraper Agent Started (Multi-Query + Exp)")
    print(f"   Queries Queued: {search_queries[:2]}")
    print(f"   Location      : {location}")
    print(f"{'='*55}")

    all_jobs = []
    
    # Restrict to maximum of 2 distinct queries to prevent API bans & excessive wait times
    for rank, query in enumerate(search_queries[:2]):
        print(f"\n   [+] Executing Pass {rank+1}/2 for query: '{query}'...")
        
        global_jobs_pan = scrape_global_jobs(query, "India", results_wanted=40)
        local_jobs_pan  = scrape_local_jobs_india(query, "India")
        remote_jobs     = scrape_remote_jobs(query)
        
        all_jobs.extend(global_jobs_pan)
        all_jobs.extend(local_jobs_pan)
        all_jobs.extend(remote_jobs)

    print(f"\n📦 Total raw jobs pulled across all queries: {len(all_jobs)}")

    # Deduplicate
    unique_jobs = deduplicate_jobs(all_jobs)

    # Save to DB
    print(f"\n💾 Saving to PostgreSQL...")
    saved = save_jobs_to_db(unique_jobs)

    print(f"\n{'='*55}")
    print(f"✅ Job Scraper Done!")
    print(f"   Total found  : {len(all_jobs)}")
    print(f"   Unique jobs  : {len(unique_jobs)}")
    print(f"   New in DB    : {saved}")
    print(f"{'='*55}\n")

    return unique_jobs


