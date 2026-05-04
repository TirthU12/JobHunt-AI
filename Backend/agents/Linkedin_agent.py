import os
import re
import json
import uuid
import time
import asyncio
import random
import sys
from typing import TypedDict, List, Optional
from dotenv import load_dotenv
import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END
# Windows-specific fix for Playwright + asyncio.create_subprocess_exec
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ─── LLM ─────────────────────────────────────────────────────────────────────
llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model="openai/gpt-oss-120b",
    temperature=0
)

# ─── LinkedIn Experience Level Codes ─────────────────────────────────────────
EXP_LEVEL_CODES = {
    "internship" : "1",
    "entry"      : "2",
    "associate"  : "3",
    "mid"        : "4",
    "senior"     : "5",
    "director"   : "6",
    "executive"  : "7",
}

# ─── Job Type Codes ───────────────────────────────────────────────────────────
JOB_TYPE_CODES = {
    "full_time" : "F",
    "part_time" : "P",
    "contract"  : "C",
    "temporary" : "T",
    "internship": "I",
    "volunteer" : "V",
    "other"     : "O",
}

# ─── Time Filter Codes ────────────────────────────────────────────────────────
TIME_FILTER_CODES = {
    24  : "r86400",       # past 24 hours
    168 : "r604800",      # past week
    720 : "r2592000",     # past month
}

# ─── User Agents ─────────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",

    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",

    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",

    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


# ══════════════════════════════════════════════════════════════════════════════
# LANGGRAPH STATE
# ══════════════════════════════════════════════════════════════════════════════

class LinkedInState(TypedDict):
    keyword         : str
    location        : str
    experience_level: str       # entry / mid / senior
    job_type        : str       # full_time / contract etc
    hours_old       : int       # 24 / 168 / 720
    raw_jobs        : List[dict]
    enriched_jobs   : List[dict]
    saved_count     : int
    search_url      : str
    error           : Optional[str]


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def build_linkedin_url(keyword: str, location: str,
                       experience_level: str, job_type: str,
                       hours_old: int) -> str:
    """Build LinkedIn jobs search URL with all filters."""

    exp_code  = EXP_LEVEL_CODES.get(experience_level, "2")
    type_code = JOB_TYPE_CODES.get(job_type, "F")
    time_code = TIME_FILTER_CODES.get(hours_old, "r86400")

    url = (
        f"https://www.linkedin.com/jobs/search/?"
        f"keywords={keyword.replace(' ', '%20')}"
        f"&location={location.replace(' ', '%20')}"
        f"&f_TPR={time_code}"
        f"&f_E={exp_code}"
        f"&f_JT={type_code}"
        f"&sortBy=DD"
        f"&position=1"
        f"&pageNum=0"
    )
    return url


def build_smart_keyword(parsed_resume: dict) -> str:
    """Build optimal LinkedIn search keyword from resume data."""
    skills    = parsed_resume.get("skills", [])
    titles    = parsed_resume.get("job_titles", [])
    
    # Use first job title if available, or build from top skills
    if titles:
        base = titles[0]
    elif skills:
        base = skills[0] + " Developer"
    else:
        base = "Software Engineer"

    # We don't add "entry level" or "senior" here because we use the f_E filter in the URL!
    return base.strip()


def detect_experience_level(exp_years: int) -> str:
    """Map years of experience to LinkedIn filter."""
    if exp_years <= 1:
        return "entry"
    elif exp_years <= 3:
        return "associate"
    elif exp_years <= 6:
        return "mid"
    else:
        return "senior"


def clean_text(text: str) -> str:
    """Clean whitespace and newlines from scraped text."""
    return re.sub(r'\s+', ' ', text or '').strip()


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1 — BUILD SEARCH URL
# ══════════════════════════════════════════════════════════════════════════════

def build_search_url_node(state: LinkedInState) -> LinkedInState:
    """Build the LinkedIn search URL with all filters applied."""

    url = build_linkedin_url(
        keyword         = state["keyword"],
        location        = state["location"],
        experience_level= state["experience_level"],
        job_type        = state["job_type"],
        hours_old       = state["hours_old"]
    )

    print(f"\n{'='*60}")
    print(f"🔍 LinkedIn Job Agent")
    print(f"   Keyword    : {state['keyword']}")
    print(f"   Location   : {state['location']}")
    print(f"   Exp Level  : {state['experience_level']}")
    print(f"   Time Filter: past {state['hours_old']} hours")
    print(f"   URL        : {url}")
    print(f"{'='*60}")

    return {**state, "search_url": url}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2 — SCRAPE LINKEDIN WITH PLAYWRIGHT
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_linkedin_async(url: str) -> list:
    """
    Scrape LinkedIn jobs using Playwright.
    Works without login for public job listings.
    """
    jobs_found = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={
                "Accept-Language": "en-IN,en;q=0.9",
                "Accept"         : "text/html,application/xhtml+xml,"
                                   "application/xml;q=0.9,*/*;q=0.8",
            }
        )

        # Block heavy resources to speed up scraping
        await context.route(
            "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,mp4,mp3}",
            lambda route: route.abort()
        )
        await context.route(
            "**/analytics**", lambda route: route.abort()
        )
        await context.route(
            "**/tracking**", lambda route: route.abort()
        )

        page = await context.new_page()

        try:
            print(f"\n🌐 Opening LinkedIn...")
            await page.goto(url, timeout=30000,
                            wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Check if redirected to login page
            current_url = page.url
            if "login" in current_url or "authwall" in current_url:
                print(f"   ⚠️  LinkedIn requires login. Using public URL...")
                # Try public jobs URL instead
                public_url = url.replace(
                    "linkedin.com/jobs/search",
                    "linkedin.com/jobs/search"
                )
                await page.goto(public_url.replace("/jobs/search/",
                                                    "/jobs-guest/jobs/"),
                                timeout=30000,
                                wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

            # Scroll down multiple times to lazy-load all jobs
            print(f"   📜 Scrolling to load all jobs...")
            for scroll in range(5):
                await page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight)"
                )
                await page.wait_for_timeout(random.randint(1000, 2000))

                # Click "Show more" button if present
                show_more = await page.query_selector(
                    "button[aria-label*='See more'], "
                    "button.infinite-scroller__show-more-button, "
                    "button[data-tracking-control-name*='public_jobs_show-more-jobs']"
                )
                if show_more:
                    await show_more.click()
                    await page.wait_for_timeout(1500)

            # ── Extract job cards ─────────────────────────────────────────────
            # Try multiple selectors — LinkedIn changes them frequently
            card_selectors = [
                "div.job-search-card",
                "li.jobs-search-results__list-item",
                "div[data-job-id]",
                ".base-card",
                "li[class*='jobs-search']",
                "div[class*='job-card']",
            ]

            job_cards = []
            for sel in card_selectors:
                job_cards = await page.query_selector_all(sel)
                if job_cards:
                    print(f"   ✅ Found {len(job_cards)} cards "
                          f"with selector: {sel}")
                    break

            if not job_cards:
                # Last resort — get all text and use AI
                print(f"   ⚠️  No cards found. Using AI extraction...")
                page_text = await page.evaluate("document.body.innerText")
                jobs_found = extract_jobs_with_ai_from_text(
                    page_text[:5000], url
                )
            else:
                # ── Parse each job card ───────────────────────────────────────
                for card in job_cards[:30]:
                    try:
                        job = await extract_job_from_card(card, page)
                        if job:
                            jobs_found.append(job)
                    except Exception:
                        continue

        except PlaywrightTimeout:
            print(f"   ❌ LinkedIn page timed out")

        except Exception as e:
            print(f"   ❌ Playwright error: {e}")

        finally:
            await browser.close()

    return jobs_found


async def extract_job_from_card(card, page) -> Optional[dict]:
    """Extract all fields from a single LinkedIn job card."""

    # ── Title ─────────────────────────────────────────────────────────────────
    title = ""
    for sel in [
        "h3.base-search-card__title",
        "h3[class*='job-title']",
        "a[class*='job-title']",
        "h3", "h4"
    ]:
        el = await card.query_selector(sel)
        if el:
            title = clean_text(await el.inner_text())
            if title:
                break

    if not title:
        return None

    # ── Company ───────────────────────────────────────────────────────────────
    company = ""
    for sel in [
        "h4.base-search-card__subtitle",
        "a[class*='company-name']",
        "span[class*='company']",
        "a[data-tracking-control-name*='company']",
        "h4"
    ]:
        el = await card.query_selector(sel)
        if el:
            company = clean_text(await el.inner_text())
            if company:
                break

    # ── Location ──────────────────────────────────────────────────────────────
    location = ""
    for sel in [
        "span.job-search-card__location",
        "[class*='job-location']",
        "[class*='location']",
        "span[class*='bullet']"
    ]:
        el = await card.query_selector(sel)
        if el:
            location = clean_text(await el.inner_text())
            if location:
                break

    # ── Job URL ───────────────────────────────────────────────────────────────
    job_url = ""
    for sel in [
        "a[href*='/jobs/view/']",
        "a[href*='linkedin.com/jobs']",
        "a[class*='job-card']",
        "a"
    ]:
        el = await card.query_selector(sel)
        if el:
            href = await el.get_attribute("href") or ""
            if "/jobs/" in href:
                # Clean tracking parameters
                job_url = href.split("?")[0]
                if job_url.startswith("/"):
                    job_url = f"https://www.linkedin.com{job_url}"
                break

    # ── Posted Time ───────────────────────────────────────────────────────────
    posted = ""
    time_el = await card.query_selector("time, [class*='listdate']")
    if time_el:
        posted = await time_el.get_attribute("datetime") or \
                 clean_text(await time_el.inner_text())

    # ── Salary (if shown) ─────────────────────────────────────────────────────
    salary = ""
    sal_el = await card.query_selector(
        "[class*='salary'], [class*='compensation']"
    )
    if sal_el:
        salary = clean_text(await sal_el.inner_text())

    # ── Job ID from URL ───────────────────────────────────────────────────────
    job_id_match = re.search(r'/jobs/view/(\d+)', job_url)
    linkedin_id  = job_id_match.group(1) if job_id_match else ""

    return {
        "id"          : str(uuid.uuid4()),
        "title"       : title,
        "company"     : company,
        "location"    : location,
        "source"      : "linkedin_playwright",
        "url"         : job_url,
        "description" : "",        # filled in enrichment node
        "salary"      : salary,
        "job_type"    : "full-time",
        "posted_at"   : posted,
        "linkedin_id" : linkedin_id,
        "is_local"    : False,
        "raw_data"    : {}
    }


def extract_jobs_with_ai_from_text(text: str, source_url: str) -> list:
    """Use Groq to extract jobs from raw page text as last resort."""
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Extract job listings from text. Return ONLY valid JSON."),
        ("human", """
        Extract all job listings from this LinkedIn page text.
        Return JSON array:
        [{{
          "title"   : "job title",
          "company" : "company name",
          "location": "location",
          "posted"  : "posted time"
        }}]
        If no jobs found return [].
        Text: {text}
        Return ONLY JSON array.
        """)
    ])
    chain = prompt | llm | parser

    try:
        result = chain.invoke({"text": text})
        jobs   = []
        if isinstance(result, list):
            for item in result:
                jobs.append({
                    "id"         : str(uuid.uuid4()),
                    "title"      : item.get("title", ""),
                    "company"    : item.get("company", ""),
                    "location"   : item.get("location", ""),
                    "source"     : "linkedin_ai_extract",
                    "url"        : source_url,
                    "description": "",
                    "salary"     : "",
                    "job_type"   : "",
                    "posted_at"  : item.get("posted", ""),
                    "is_local"   : False,
                    "raw_data"   : {}
                })
        return jobs
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2 — SCRAPE LINKEDIN WITH PLAYWRIGHT
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_description_async(job_url: str) -> str:
    """Fetch full job description from LinkedIn job page."""
    if not job_url or "linkedin.com" not in job_url:
        return ""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS)
        )
        page = await context.new_page()

        try:
            await page.goto(job_url, timeout=20000,
                            wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # Try to click "Show more" to expand description
            show_more = await page.query_selector(
                "button[aria-label*='more'], "
                ".show-more-less-html__button"
            )
            if show_more:
                await show_more.click()
                await page.wait_for_timeout(500)

            # Extract description
            for sel in [
                ".show-more-less-html__markup",
                ".description__text",
                "[class*='job-description']",
                "#job-details",
                "section.description"
            ]:
                el = await page.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    if text:
                        return clean_text(text)[:3000]

        except Exception:
            pass
        finally:
            await browser.close()

    return ""


import threading

def run_playwright_windows_safe(coro):
    """
    Helper to run Playwright in a separate thread with a Proactor loop.
    This bypasses Windows NotImplementedError in mixed async environments.
    """
    result_container = []
    exception_container = []

    def _wrapper():
        try:
            # Force Proactor loop in this thread
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result_container.append(loop.run_until_complete(coro))
            finally:
                loop.close()
        except Exception as e:
            exception_container.append(e)

    thread = threading.Thread(target=_wrapper)
    thread.start()
    thread.join()

    if exception_container:
        raise exception_container[0]
    return result_container[0]


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2 — SCRAPE LINKEDIN WITH PLAYWRIGHT
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_linkedin_node(state: LinkedInState) -> LinkedInState:
    """Node wrapper for async LinkedIn scraping."""
    print(f"\n🤖 Playwright scraping LinkedIn...")

    try:
        # Run in a separate thread to avoid loop conflicts on Windows
        jobs = await asyncio.to_thread(
            run_playwright_windows_safe, 
            scrape_linkedin_async(state["search_url"])
        )
        print(f"   ✅ Playwright found: {len(jobs)} jobs")
        return {**state, "raw_jobs": jobs}

    except Exception as e:
        print(f"   ❌ Playwright failed: {e}")
        print(f"   🔄 Falling back to Serper.dev...")
        return {**state, "raw_jobs": [], "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3 — SERPER FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

def serper_fallback_node(state: LinkedInState) -> LinkedInState:
    """
    If Playwright fails or finds 0 jobs,
    use Serper.dev to search LinkedIn via Google.
    """
    if state["raw_jobs"]:
        return state  # Playwright worked, skip this node

    print(f"\n🔄 Using Serper.dev fallback...")
    serper_key = os.getenv("SERPER_API_KEY")

    if not serper_key:
        print(f"   ⚠️  No SERPER_API_KEY in .env. Skipping fallback.")
        return state

    # Time filter for Google
    time_map = {24: "qdr:d", 168: "qdr:w", 720: "qdr:m"}
    tbs      = time_map.get(state["hours_old"], "qdr:d")

    query = (
        f'site:linkedin.com/jobs '
        f'{state["keyword"]} '
        f'{state["location"]}'
    )

    try:
        import httpx
        res = httpx.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY"   : serper_key,
                "Content-Type": "application/json"
            },
            json={
                "q"  : query,
                "gl" : "in",
                "hl" : "en",
                "num": 20,
                "tbs": tbs
            },
            timeout=15
        )
        organic = res.json().get("organic", [])
        jobs    = []

        for r in organic:
            title = r.get("title", "").split(" - LinkedIn")[0]
            jobs.append({
                "id"         : str(uuid.uuid4()),
                "title"      : clean_text(title),
                "company"    : "",
                "location"   : state["location"],
                "source"     : "linkedin_serper",
                "url"        : r.get("link", ""),
                "description": r.get("snippet", "")[:1000],
                "salary"     : "",
                "job_type"   : "",
                "posted_at"  : "",
                "is_local"   : False,
                "raw_data"   : {}
            })

        print(f"   ✅ Serper found: {len(jobs)} LinkedIn jobs")
        return {**state, "raw_jobs": jobs}

    except Exception as e:
        print(f"   ❌ Serper also failed: {e}")
        return state


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4 — GET JOB DESCRIPTIONS
# ══════════════════════════════════════════════════════════════════════════════

async def enrich_with_descriptions_node(state: LinkedInState) -> LinkedInState:
    """
    Fetch full job description for top 10 jobs.
    Adds description so AI matcher can score properly.
    """
    jobs = state["raw_jobs"]

    if not jobs:
        return {**state, "enriched_jobs": []}

    print(f"\n📄 Fetching descriptions for top 10 jobs...")
    
    # Use the safe runner to fetch descriptions one by one or in small batches
    # We use a separate thread for the whole batch for simplicity on Windows
    async def fetch_batch():
        enriched_list = []
        for job in jobs[:10]:
            desc = await fetch_description_async(job.get("url", ""))
            job["description"] = desc
            enriched_list.append(job)
            await asyncio.sleep(1) # Slight delay to avoid blocks
        return enriched_list

    try:
        enriched_top = await asyncio.to_thread(
            run_playwright_windows_safe, 
            fetch_batch()
        )
        enriched = enriched_top + jobs[10:]
    except Exception as e:
        print(f"   ⚠️ Description enrichment failed: {e}")
        enriched = jobs

    print(f"   ✅ Enriched {len(enriched)} jobs")
    return {**state, "enriched_jobs": enriched}



# ══════════════════════════════════════════════════════════════════════════════
# NODE 5 — DEDUPLICATE
# ══════════════════════════════════════════════════════════════════════════════

def deduplicate_node(state: LinkedInState) -> LinkedInState:
    """Remove duplicate jobs by URL and title+company combo."""
    jobs     = state["enriched_jobs"] or state["raw_jobs"]
    seen_url = set()
    seen_tc  = set()
    unique   = []

    for job in jobs:
        url = job.get("url", "").split("?")[0]
        tc  = f"{job.get('title','')}|{job.get('company','')}".lower()

        if url and url in seen_url:
            continue
        if tc in seen_tc:
            continue

        if url:
            seen_url.add(url)
        seen_tc.add(tc)
        unique.append(job)

    print(f"\n🧹 Dedup: {len(jobs)} → {len(unique)} unique jobs")
    return {**state, "enriched_jobs": unique}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 6 — SAVE TO POSTGRESQL
# ══════════════════════════════════════════════════════════════════════════════

def save_jobs_node(state: LinkedInState) -> LinkedInState:
    """Save LinkedIn jobs to the linkedin_jobs table."""
    from db.connection import get_db_connection

    jobs  = state["enriched_jobs"]
    if not jobs:
        print("   ⚠️  No jobs to save")
        return {**state, "saved_count": 0}

    print(f"\n💾 Saving {len(jobs)} LinkedIn jobs to PostgreSQL...")

    db    = get_db_connection()
    cur   = db.cursor()
    saved = 0

    try:
        # Create table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS linkedin_jobs (
                id VARCHAR(255) PRIMARY KEY,
                title VARCHAR(500),
                company VARCHAR(255),
                location VARCHAR(255),
                source VARCHAR(100),
                url VARCHAR(1000) UNIQUE,
                description TEXT,
                salary VARCHAR(255),
                job_type VARCHAR(100),
                raw_data JSONB,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                match_score INTEGER DEFAULT 0,
                match_reason TEXT,
                apply_recommendation VARCHAR(255)
            )
        """)
        db.commit()

        # Migration: ensure all columns exist
        columns_to_check = {
            "salary": "VARCHAR(255)",
            "raw_data": "JSONB",
            "scraped_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "match_score": "INTEGER DEFAULT 0",
            "match_reason": "TEXT",
            "apply_recommendation": "VARCHAR(255)"
        }
        for col, col_type in columns_to_check.items():
            try:
                cur.execute(f"""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='linkedin_jobs' AND column_name=%s
                """, (col,))
                if not cur.fetchone():
                    print(f"   🔧 Migrating: Adding {col} to linkedin_jobs")
                    cur.execute(f"ALTER TABLE linkedin_jobs ADD COLUMN {col} {col_type}")
                    db.commit()
            except Exception as e:
                print(f"   ⚠️ Migration error for {col}: {e}")
                db.rollback()

        db.commit()

        for job in jobs:
            try:
                cur.execute("SAVEPOINT sp")
                cur.execute("""
                    INSERT INTO linkedin_jobs
                        (id, title, company, location, source,
                         url, description, salary, job_type, raw_data)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (url) DO UPDATE SET
                        title = EXCLUDED.title,
                        company = EXCLUDED.company,
                        scraped_at = CURRENT_TIMESTAMP
                """, (
                    str(uuid.uuid4()),
                    job.get("title",      "")[:500],
                    job.get("company",    "")[:255],
                    job.get("location",   "")[:255],
                    job.get("source",     "linkedin")[:100],
                    job.get("url",        "")[:1000],
                    job.get("description","")[:5000],
                    job.get("salary",     "")[:255],
                    job.get("job_type",   "")[:100],
                    json.dumps({
                        "posted_at"  : job.get("posted_at", ""),
                        "linkedin_id": job.get("linkedin_id", ""),
                        "source"     : job.get("source", "linkedin_playwright")
                    })
                ))
                cur.execute("RELEASE SAVEPOINT sp")
                saved += 1

            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                print(f"   ⚠️  Skip '{job.get('title','')}': {e}")
                continue

        db.commit()
        print(f"   ✅ Saved/Updated {saved} LinkedIn jobs")

    except Exception as e:
        db.rollback()
        print(f"   ❌ DB error: {e}")

    finally:
        cur.close()
        db.close()

    return {**state, "saved_count": saved}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 7 — SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def summary_node(state: LinkedInState) -> LinkedInState:
    """Print final summary of LinkedIn search."""
    jobs = state["enriched_jobs"]

    print(f"\n{'='*60}")
    print(f"✅ LinkedIn Agent Summary")
    print(f"{'='*60}")
    print(f"   Keyword    : {state['keyword']}")
    print(f"   Location   : {state['location']}")
    print(f"   Time Filter: past {state['hours_old']} hours")
    print(f"   Found      : {len(jobs)} jobs")
    print(f"   Saved      : {state['saved_count']} new to DB")

    # Source breakdown
    sources = {}
    for j in jobs:
        s = j.get("source", "unknown")
        sources[s] = sources.get(s, 0) + 1
    print(f"\n   Sources:")
    for s, c in sources.items():
        print(f"      {s}: {c}")

    print(f"\n   Top results:")
    for job in jobs[:5]:
        print(f"   💼 {job.get('title','')}")
        print(f"      🏢 {job.get('company','')} | "
              f"📍 {job.get('location','')} | "
              f"🕐 {job.get('posted_at','')}")
        print(f"      🔗 {job.get('url','')}")
        print()

    print(f"{'='*60}\n")
    return state


# ══════════════════════════════════════════════════════════════════════════════
# BUILD LANGGRAPH PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def build_linkedin_graph():
    """Build LangGraph pipeline for LinkedIn job search."""
    graph = StateGraph(LinkedInState)

    graph.add_node("build_url"    , build_search_url_node)
    graph.add_node("scrape"       , scrape_linkedin_node)
    graph.add_node("fallback"     , serper_fallback_node)
    graph.add_node("descriptions" , enrich_with_descriptions_node)
    graph.add_node("deduplicate"  , deduplicate_node)
    graph.add_node("save"         , save_jobs_node)
    graph.add_node("summary"      , summary_node)

    graph.set_entry_point("build_url")
    graph.add_edge("build_url"  , "scrape")
    graph.add_edge("scrape"     , "fallback")
    graph.add_edge("fallback"   , "descriptions")
    graph.add_edge("descriptions", "deduplicate")
    graph.add_edge("deduplicate", "save")
    graph.add_edge("save"       , "summary")
    graph.add_edge("summary"    , END)

    return graph.compile()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION — CALL THIS FROM OTHER AGENTS
# ══════════════════════════════════════════════════════════════════════════════

async def search_linkedin_jobs(
    parsed_resume   : dict,
    hours_old       : int = 24,
    fetch_descriptions: bool = True
) -> list:
    """
    Full LangGraph LinkedIn search pipeline.
    """
    # Build keyword from resume
    keyword  = build_smart_keyword(parsed_resume)
    location = parsed_resume.get("location", "India").split(",")[0]
    exp_yrs  = parsed_resume.get("experience_years", 0)
    exp_lvl  = detect_experience_level(exp_yrs)

    pipeline    = build_linkedin_graph()
    final_state = await pipeline.ainvoke({
        "keyword"         : keyword,
        "location"        : location,
        "experience_level": exp_lvl,
        "job_type"        : "full_time",
        "hours_old"       : hours_old,
        "raw_jobs"        : [],
        "enriched_jobs"   : [],
        "saved_count"     : 0,
        "search_url"      : "",
        "error"           : None
    })

    return final_state["enriched_jobs"]


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM SEARCH — USER CAN PASS OWN KEYWORD
# ══════════════════════════════════════════════════════════════════════════════

async def custom_linkedin_search(
    keyword         : str,
    location        : str = "India",
    experience_level: str = "entry",
    job_type        : str = "full_time",
    hours_old       : int = 24
) -> list:
    """
    Custom LinkedIn search — user provides keyword directly.
    """
    pipeline    = build_linkedin_graph()
    final_state = await pipeline.ainvoke({
        "keyword"         : keyword,
        "location"        : location,
        "experience_level": experience_level,
        "job_type"        : job_type,
        "hours_old"       : hours_old,
        "raw_jobs"        : [],
        "enriched_jobs"   : [],
        "saved_count"     : 0,
        "search_url"      : "",
        "error"           : None
    })

    return final_state["enriched_jobs"]


# ══════════════════════════════════════════════════════════════════════════════
# RUN DIRECTLY TO TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    async def main():
        # Test 1 — Custom keyword search
        print("Test 1 — Custom keyword search")
        jobs = await custom_linkedin_search(
            keyword          = "entry level MERN stack developer",
            location         = "India",
            experience_level = "entry",
            job_type         = "full_time",
            hours_old        = 24
        )
        print(f"\n✅ Found {len(jobs)} jobs")

    asyncio.run(main())