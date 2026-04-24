import os
import re
import json
import uuid
import asyncio
import time
from typing import TypedDict, List, Optional
from dotenv import load_dotenv

from jobspy import scrape_jobs
from ddgs import DDGS
from ddgs.exceptions import DDGSException
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END

load_dotenv()

# ─── LangChain LLM ───────────────────────────────────────────────────────────
llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model="openai/gpt-oss-120b",
    temperature=0
)


# ══════════════════════════════════════════════════════════════════════════════
# LANGGRAPH STATE
# ══════════════════════════════════════════════════════════════════════════════

class LocalJobState(TypedDict):
    job_title       : str
    city            : str
    skills          : List[str]
    industry        : str
    local_companies : List[dict]     # found by company discovery
    board_jobs      : List[dict]     # from job boards city filter
    website_jobs    : List[dict]     # from company career pages
    all_local_jobs  : List[dict]     # merged + deduplicated
    saved_count     : int
    error           : Optional[str]


# ══════════════════════════════════════════════════════════════════════════════
# HELPER — Safe DuckDuckGo search with retry
# ══════════════════════════════════════════════════════════════════════════════

def safe_ddg_search(query: str, max_results: int = 10,
                    retries: int = 3) -> list:
    """DuckDuckGo search with retry on rate limit."""
    for attempt in range(retries):
        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=max_results)
                return results or []
        except DDGSException:
            wait = (attempt + 1) * 5
            print(f"   ⚠️  DDG rate limited. Waiting {wait}s...")
            time.sleep(wait)
        except Exception as e:
            print(f"   ⚠️  DDG error: {e}")
            return []
    return []


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1 — DISCOVER LOCAL COMPANIES IN THE CITY
# ══════════════════════════════════════════════════════════════════════════════

def discover_local_companies_node(state: LocalJobState) -> LocalJobState:
    """
    Find local companies in the user's city using DuckDuckGo.
    Searches multiple queries to find as many local companies as possible.
    """
    city     = state["city"]
    industry = state["industry"]
    print(f"\n🏙️  Discovering local companies in {city}...")

    all_companies = []
    seen_domains  = set()

    # Multiple search queries to find different companies
    queries = [
        f"top {industry} companies in {city} India",
        f"software IT companies in {city} Gujarat hiring",
        f"best tech startups in {city} India 2024",
        f"{industry} companies {city} careers jobs",
        f"IT firms {city} India employee review",
    ]

    for query in queries:
        results = safe_ddg_search(query, max_results=10)
        time.sleep(2)  # be polite

        for r in results:
            url    = r.get("href", "")
            title  = r.get("title", "")
            domain = extract_domain(url)

            # Skip job boards and generic sites
            skip_domains = [
                "linkedin.com", "naukri.com", "indeed.com",
                "glassdoor.com", "shine.com", "timesjobs.com",
                "internshala.com", "foundit.in", "wikipedia.org",
                "justdial.com", "indiamart.com", "facebook.com",
                "twitter.com", "instagram.com", "youtube.com"
            ]
            if any(skip in domain for skip in skip_domains):
                continue

            if domain and domain not in seen_domains:
                seen_domains.add(domain)
                company_name = extract_company_name(title, domain)
                all_companies.append({
                    "name"   : company_name,
                    "domain" : domain,
                    "url"    : url,
                    "source" : "duckduckgo"
                })

    # Also use LLM to generate known company names for the city
    llm_companies = get_llm_company_list(city, industry)
    for comp in llm_companies:
        domain = comp.get("domain", "")
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            all_companies.append(comp)

    print(f"   ✅ Found {len(all_companies)} local companies in {city}")
    for c in all_companies[:5]:
        print(f"      - {c['name']} ({c['domain']})")

    return {**state, "local_companies": all_companies}


def extract_domain(url: str) -> str:
    """Extract clean domain from URL."""
    try:
        match = re.search(
            r'(?:https?://)?(?:www\.)?([a-zA-Z0-9\-]+\.[a-zA-Z]{2,})',
            url
        )
        return match.group(1).lower() if match else ""
    except Exception:
        return ""


def extract_company_name(title: str, domain: str) -> str:
    """Extract company name from page title or domain."""
    # Try from title first
    name = title.split("-")[0].split("|")[0].strip()
    if len(name) > 3:
        return name

    # Fallback to domain name
    return domain.split(".")[0].title()


def get_llm_company_list(city: str, industry: str) -> list:
    """Ask Groq to list known companies in the city."""
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a business directory expert. Return ONLY valid JSON."),
        ("human", """List 10 real {industry} companies located in {city}, India.
        Return JSON array only:
        [
          {{"name": "Company Name", "domain": "company.com"}},
          ...
        ]
        Only include companies actually based in {city}.
        Return ONLY JSON array, no explanation.""")
    ])
    chain = prompt | llm | parser

    try:
        result = chain.invoke({"city": city, "industry": industry})
        return result if isinstance(result, list) else []
    except Exception as e:
        print(f"   ⚠️  LLM company list failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2 — SCRAPE JOB BOARDS WITH CITY FILTER
# ══════════════════════════════════════════════════════════════════════════════

def scrape_local_boards_node(state: LocalJobState) -> LocalJobState:
    """
    Scrape major job boards filtered by city.
    Uses JobSpy + DuckDuckGo site search.
    """
    job_title = state["job_title"]
    city      = state["city"]
    print(f"\n📋 Scraping job boards for {job_title} in {city}...")

    all_board_jobs = []

    # ── JobSpy city-filtered search ──────────────────────────────────────────
    try:
        jobs_df = scrape_jobs(
            site_name      = ["linkedin", "indeed", "glassdoor"],
            search_term    = job_title,
            location       = f"{city}, India",
            results_wanted = 30,
            country_indeed = "India",
            hours_old      = 168        # last 7 days
        )

        if jobs_df is not None and not jobs_df.empty:
            for _, row in jobs_df.iterrows():
                job = build_job_dict(row, is_local=True, city=city)
                if job["title"] and job["url"]:
                    all_board_jobs.append(job)

            print(f"   ✅ JobSpy city: {len(all_board_jobs)} jobs")

    except Exception as e:
        print(f"   ⚠️  JobSpy error: {e}")

    # ── DuckDuckGo site-specific searches ────────────────────────────────────
    boards = [
        ("naukri.com"     , f'site:naukri.com "{job_title}" "{city}"'),
        ("internshala.com", f'site:internshala.com "{job_title}" "{city}"'),
        ("shine.com"      , f'site:shine.com "{job_title}" "{city}"'),
        ("timesjobs.com"  , f'site:timesjobs.com "{job_title}" "{city}"'),
        ("foundit.in"     , f'site:foundit.in "{job_title}" "{city}"'),
    ]

    for board_name, query in boards:
        results = safe_ddg_search(query, max_results=10)
        time.sleep(2)

        for r in results:
            all_board_jobs.append({
                "id"         : str(uuid.uuid4()),
                "title"      : clean_title(r.get("title", "")),
                "company"    : "",
                "location"   : city,
                "source"     : board_name,
                "url"        : r.get("href", ""),
                "description": r.get("body", "")[:2000],
                "salary"     : "",
                "job_type"   : "",
                "is_local"   : True,
                "city"       : city,
                "raw_data"   : {}
            })

        print(f"   ✅ {board_name}: {len(results)} jobs")
        time.sleep(1)

    print(f"   📦 Total board jobs: {len(all_board_jobs)}")
    return {**state, "board_jobs": all_board_jobs}


def build_job_dict(row, is_local: bool, city: str) -> dict:
    """Convert a JobSpy DataFrame row to our job dict format."""
    return {
        "id"         : str(uuid.uuid4()),
        "title"      : clean_title(str(row.get("title", ""))),
        "company"    : str(row.get("company", "")).strip(),
        "location"   : str(row.get("location", city)).strip(),
        "source"     : str(row.get("site", "")).strip(),
        "url"        : str(row.get("job_url", "")).strip(),
        "description": str(row.get("description", ""))[:5000],
        "salary"     : f"{row.get('min_amount','')} - {row.get('max_amount','')}",
        "job_type"   : str(row.get("job_type", "")).strip(),
        "is_local"   : is_local,
        "city"       : city,
        "raw_data"   : {}
    }


def clean_title(title: str) -> str:
    """Remove noise words from job titles."""
    noise = [
        "urgent", "hiring", "immediately", "walk-in",
        "openings", "vacancy", "apply now", "fresher"
    ]
    for word in noise:
        title = re.sub(word, "", title, flags=re.IGNORECASE)
    return title.strip(" -|")


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3 — SCRAPE COMPANY CAREER PAGES WITH PLAYWRIGHT
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_single_career_page(company: dict,
                                    job_title: str,
                                    city: str) -> list:
    """Scrape a single company's career page using Playwright."""
    from playwright.async_api import async_playwright

    domain       = company.get("domain", "")
    company_name = company.get("name", "")
    jobs_found   = []

    # Try common career page URLs
    career_urls = [
        f"https://{domain}/careers",
        f"https://{domain}/jobs",
        f"https://{domain}/career",
        f"https://www.{domain}/careers",
        f"https://www.{domain}/jobs",
        f"https://{domain}/join-us",
        f"https://{domain}/work-with-us",
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()

        # Set realistic browser headers
        await page.set_extra_http_headers({
            "User-Agent"      : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language" : "en-US,en;q=0.9",
        })

        for career_url in career_urls:
            try:
                await page.goto(career_url, timeout=15000,
                                wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)

                # Check page has content
                content = await page.content()
                if len(content) < 500:
                    continue

                # Try multiple CSS selectors for job listings
                selectors = [
                    ".job-listing", ".careers-item", ".job-card",
                    ".position", ".opening", "article.job",
                    "[class*='job']", "[class*='career']",
                    "[class*='position']", "[class*='opening']",
                    "li.job", "div.job", ".vacancy"
                ]

                items = []
                for selector in selectors:
                    items = await page.query_selector_all(selector)
                    if len(items) > 0:
                        break

                if items:
                    for item in items[:20]:
                        try:
                            text     = await item.inner_text()
                            link_el  = await item.query_selector("a")
                            href     = ""
                            if link_el:
                                href = await link_el.get_attribute("href") or ""
                                if href and not href.startswith("http"):
                                    href = f"https://{domain}{href}"

                            if text and len(text) > 5:
                                jobs_found.append({
                                    "id"         : str(uuid.uuid4()),
                                    "title"      : clean_title(text.split("\n")[0][:200]),
                                    "company"    : company_name,
                                    "location"   : city,
                                    "source"     : "company_website",
                                    "url"        : href or career_url,
                                    "description": text[:3000],
                                    "salary"     : "",
                                    "job_type"   : "",
                                    "is_local"   : True,
                                    "city"       : city,
                                    "raw_data"   : {"scraped_from": career_url}
                                })
                        except Exception:
                            continue

                # If no structured items — use AI to extract from HTML
                if not jobs_found:
                    page_text = await page.evaluate(
                        "document.body.innerText"
                    )
                    if page_text and len(page_text) > 200:
                        ai_jobs = extract_jobs_with_ai(
                            page_text[:3000],
                            company_name,
                            city,
                            career_url
                        )
                        jobs_found.extend(ai_jobs)

                if jobs_found:
                    print(f"      ✅ {company_name}: {len(jobs_found)} jobs")
                    break  # found jobs, stop trying other URLs

            except Exception as e:
                continue  # try next URL

        await browser.close()

    return jobs_found


def extract_jobs_with_ai(page_text: str, company: str,
                         city: str, url: str) -> list:
    """Use Groq to extract job listings from raw page text."""
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Extract job listings from text. Return ONLY valid JSON."),
        ("human", """Find all job openings in this text.
        Return JSON array:
        [
          {{"title": "job title", "description": "brief description"}}
        ]
        If no jobs found return empty array [].
        Text: {text}
        Return ONLY JSON array.""")
    ])
    chain = prompt | llm | parser

    try:
        result = chain.invoke({"text": page_text})
        jobs   = []

        if isinstance(result, list):
            for item in result:
                if item.get("title"):
                    jobs.append({
                        "id"         : str(uuid.uuid4()),
                        "title"      : clean_title(item.get("title", "")),
                        "company"    : company,
                        "location"   : city,
                        "source"     : "company_website",
                        "url"        : url,
                        "description": item.get("description", "")[:2000],
                        "salary"     : "",
                        "job_type"   : "",
                        "is_local"   : True,
                        "city"       : city,
                        "raw_data"   : {}
                    })
        return jobs

    except Exception:
        return []


async def scrape_all_career_pages_async(
        companies: list, job_title: str, city: str) -> list:
    """Scrape multiple company career pages concurrently."""
    print(f"\n🌐 Scraping {len(companies)} company career pages...")

    # Limit to 10 companies to avoid overwhelming
    companies_to_scrape = companies[:10]
    all_website_jobs    = []

    # Run scraping with semaphore to limit concurrency
    semaphore = asyncio.Semaphore(3)  # max 3 at a time

    async def scrape_with_limit(company):
        async with semaphore:
            jobs = await scrape_single_career_page(
                company, job_title, city
            )
            await asyncio.sleep(1)  # polite delay
            return jobs

    tasks   = [scrape_with_limit(c) for c in companies_to_scrape]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, list):
            all_website_jobs.extend(result)

    print(f"   ✅ Career pages: {len(all_website_jobs)} jobs found")
    return all_website_jobs


def scrape_career_pages_node(state: LocalJobState) -> LocalJobState:
    """Node wrapper for async career page scraping."""
    companies   = state["local_companies"]
    job_title   = state["job_title"]
    city        = state["city"]

    if not companies:
        print("   ⚠️  No companies to scrape")
        return {**state, "website_jobs": []}

    import threading

    website_jobs = []
    
    def _run_async():
        nonlocal website_jobs
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            website_jobs = loop.run_until_complete(
                scrape_all_career_pages_async(companies, job_title, city)
            )
        except Exception as e:
            print(f"   ⚠️  Playwright local scraper thread failed: {e}")
            website_jobs = []
        finally:
            try:
                loop.close()
            except Exception:
                pass
            
    thread = threading.Thread(target=_run_async)
    thread.start()
    thread.join()

    return {**state, "website_jobs": website_jobs}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4 — MERGE + DEDUPLICATE ALL LOCAL JOBS
# ══════════════════════════════════════════════════════════════════════════════

def merge_and_deduplicate_node(state: LocalJobState) -> LocalJobState:
    """Merge board jobs + website jobs and remove duplicates."""
    board_jobs   = state["board_jobs"]
    website_jobs = state["website_jobs"]

    print(f"\n🔀 Merging all local jobs...")
    print(f"   Board jobs    : {len(board_jobs)}")
    print(f"   Website jobs  : {len(website_jobs)}")

    all_jobs  = board_jobs + website_jobs
    seen_urls = set()
    unique    = []

    for job in all_jobs:
        url = job.get("url", "").strip()

        # Remove jobs with no title or URL
        if not job.get("title") or not url:
            continue

        # Deduplicate by URL
        if url not in seen_urls:
            seen_urls.add(url)
            unique.append(job)

    print(f"   ✅ After dedup : {len(all_jobs)} → {len(unique)} unique jobs")
    return {**state, "all_local_jobs": unique}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 5 — SAVE LOCAL JOBS TO POSTGRESQL
# ══════════════════════════════════════════════════════════════════════════════

def save_local_jobs_node(state: LocalJobState) -> LocalJobState:
    """Save all local jobs to the jobs table with is_local=true."""
    from db.connection import get_db_connection

    jobs  = state["all_local_jobs"]
    print(f"\n💾 Saving {len(jobs)} local jobs to PostgreSQL...")

    if not jobs:
        return state

    db    = get_db_connection()
    cur   = db.cursor()
    saved = 0

    try:
        for job in jobs:
            try:
                cur.execute("""
                    INSERT INTO local_jobs
                        (id, title, company, location, source, source_type,
                         url, description, salary, job_type,
                         city, raw_data)
                    VALUES
                        (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (url) DO NOTHING
                """, (
                    str(uuid.uuid4()),
                    job.get("title", "")[:500],
                    job.get("company", "")[:255],
                    job.get("location", "")[:255],
                    job.get("source", "")[:100],
                    "website" if job.get("source") == "company_website" else "board",
                    job.get("url", "")[:1000],
                    job.get("description", "")[:5000],
                    job.get("salary", "")[:255],
                    job.get("job_type", "")[:100],
                    job.get("city", "")[:100],
                    json.dumps(job.get("raw_data", {}))
                ))
                if cur.rowcount > 0:
                    saved += 1

            except Exception as e:
                print(f"   ⚠️  Skip: {job.get('title','')} — {e}")
                continue

        db.commit()
        print(f"   ✅ Saved {saved} new local jobs")

    except Exception as e:
        db.rollback()
        print(f"   ❌ DB error: {e}")

    finally:
        cur.close()
        db.close()

    return {**state, "saved_count": saved}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 6 — PRINT SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def summary_node(state: LocalJobState) -> LocalJobState:
    """Print a summary of all local jobs found."""
    jobs = state["all_local_jobs"]

    print(f"\n{'='*55}")
    print(f"✅ Local Job Finder Summary for {state['city']}")
    print(f"{'='*55}")
    print(f"   Companies found : {len(state['local_companies'])}")
    print(f"   Board jobs      : {len(state['board_jobs'])}")
    print(f"   Website jobs    : {len(state['website_jobs'])}")
    print(f"   Total unique    : {len(jobs)}")
    print(f"   Saved to DB     : {state['saved_count']}")

    # Show source breakdown
    sources = {}
    for job in jobs:
        src = job.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1

    print(f"\n   By source:")
    for src, count in sorted(sources.items(),
                             key=lambda x: x[1], reverse=True):
        print(f"      {src}: {count} jobs")

    print(f"\n   Sample jobs:")
    for job in jobs[:5]:
        icon = "🌐" if job.get("source") == "company_website" else "📋"
        print(f"   {icon} {job['title']} @ {job['company']} [{job['source']}]")

    print(f"{'='*55}\n")
    return state


# ══════════════════════════════════════════════════════════════════════════════
# BUILD LANGGRAPH PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def build_local_job_graph():
    """Build LangGraph state machine for local job finding."""

    graph = StateGraph(LocalJobState)

    # Add all nodes
    graph.add_node("discover_companies" , discover_local_companies_node)
    graph.add_node("scrape_boards"      , scrape_local_boards_node)
    graph.add_node("scrape_career_pages", scrape_career_pages_node)
    graph.add_node("merge_deduplicate"  , merge_and_deduplicate_node)
    graph.add_node("save_jobs"          , save_local_jobs_node)
    graph.add_node("summary"            , summary_node)

    # Entry point
    graph.set_entry_point("discover_companies")

    # Edges — discover → both scrapers run in sequence
    graph.add_edge("discover_companies" , "scrape_boards")
    graph.add_edge("scrape_boards"      , "scrape_career_pages")
    graph.add_edge("scrape_career_pages", "merge_deduplicate")
    graph.add_edge("merge_deduplicate"  , "save_jobs")
    graph.add_edge("save_jobs"          , "summary")
    graph.add_edge("summary"            , END)

    return graph.compile()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION — CALL THIS FROM OTHER AGENTS
# ══════════════════════════════════════════════════════════════════════════════

def find_local_jobs(parsed_resume: dict) -> list:
    """
    Full LangGraph pipeline:
    1. Discover local companies in user's city
    2. Scrape job boards with city filter
    3. Scrape company career pages directly
    4. Merge + deduplicate all jobs
    5. Save to PostgreSQL with is_local=True

    Returns list of all unique local jobs found.
    """
    # Extract info from resume
    city = parsed_resume.get("location", "").split(",")[0].strip()
    if not city:
        print("⚠️  No city found in resume. Using 'Rajkot' as default.")
        city = "Bangluru"

    # Collect top queries from user data
    search_queries = []
    if parsed_resume.get("search_keywords"):
        search_queries.extend(parsed_resume["search_keywords"][:2])
    if parsed_resume.get("job_titles"):
        search_queries.extend(parsed_resume["job_titles"][:2])
    
    # Deduplicate
    search_queries = list(dict.fromkeys([q.strip() for q in search_queries if q.strip()]))
    if not search_queries:
        skills    = parsed_resume.get("skills", [])
        search_queries = [skills[0] + " developer" if skills else "software engineer"]

    # Detect industry from skills
    skills   = parsed_resume.get("skills", [])
    industry = detect_industry(skills)

    print(f"\n{'='*55}")
    print(f"🚀 Local Job Finder Agent Started (Multi-Query)")
    print(f"   City     : {city}")
    print(f"   Queries  : {search_queries[:2]}")
    print(f"   Industry : {industry}")
    print(f"{'='*55}")

    # Build and run graph
    pipeline = build_local_job_graph()
    
    aggregated_local_jobs = []

    # Restrict to maximum 2 passes
    for rank, query in enumerate(search_queries[:2]):
        print(f"\n   [+] Executing Graph Pipeline {rank+1}/2 for query: '{query}'...")
        final_state = pipeline.invoke({
            "job_title"      : query,
            "city"           : city,
            "skills"         : skills,
            "industry"       : industry,
            "local_companies": [],
            "board_jobs"     : [],
            "website_jobs"   : [],
            "all_local_jobs" : [],
            "saved_count"    : 0,
            "error"          : None
        })
        aggregated_local_jobs.extend(final_state.get("all_local_jobs", []))

    # Deduplicate globally across all query passes
    seen_urls = set()
    global_unique = []
    for job in aggregated_local_jobs:
        url = job.get("job_url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            global_unique.append(job)

    return global_unique


def detect_industry(skills: list) -> str:
    """Detect industry from resume skills."""
    skill_str = " ".join(skills).lower()

    if any(s in skill_str for s in ["python","java","react","node","django"]):
        return "software"
    elif any(s in skill_str for s in ["figma","ui","ux","design","photoshop"]):
        return "design"
    elif any(s in skill_str for s in ["data","ml","ai","tensorflow","pandas"]):
        return "data science"
    elif any(s in skill_str for s in ["seo","marketing","content","social media"]):
        return "digital marketing"
    elif any(s in skill_str for s in ["accounting","finance","tally","gst"]):
        return "finance"
    else:
        return "IT"


