import os
import re
import json
import uuid
import asyncio
import time
from typing import TypedDict, List, Optional
from dotenv import load_dotenv

import httpx
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END

load_dotenv()

# ─── LLM ─────────────────────────────────────────────────────────────────────
llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model="openai/gpt-oss-120b",
    temperature=0
)


# ══════════════════════════════════════════════════════════════════════════════
# COMPANY LISTS
# ══════════════════════════════════════════════════════════════════════════════

# ── Greenhouse ATS — free public API, no key needed ───────────────────────────
GREENHOUSE_COMPANIES = [
    {"name": "Swiggy",          "token": "swiggy"},
    {"name": "Razorpay",        "token": "razorpay"},
    {"name": "Meesho",          "token": "meesho"},
    {"name": "CRED",            "token": "cred"},
    {"name": "Groww",           "token": "groww"},
    {"name": "Freshworks",      "token": "freshworks"},
    {"name": "Postman",         "token": "postman"},
    {"name": "Browserstack",    "token": "browserstack"},
    {"name": "Chargebee",       "token": "chargebee"},
    {"name": "Hasura",          "token": "hasura"},
    {"name": "Setu",            "token": "setu"},
    {"name": "Niyo",            "token": "niyo"},
    {"name": "Darwinbox",       "token": "darwinbox"},
    {"name": "Clevertap",       "token": "clevertap"},
    {"name": "Moengage",        "token": "moengage"},
    {"name": "Druva",           "token": "druva"},
    {"name": "Icertis",         "token": "icertis"},
    {"name": "Pubmatic",        "token": "pubmatic"},
    {"name": "Netcracker",      "token": "netcracker"},
    {"name": "Mindtickle",      "token": "mindtickle"},
]

# ── Lever ATS — free public API, no key needed ────────────────────────────────
LEVER_COMPANIES = [
    {"name": "Lenskart",        "slug": "lenskart"},
    {"name": "Nykaa",           "slug": "nykaatech"},
    {"name": "Cashfree",        "slug": "cashfree"},
    {"name": "FamPay",          "slug": "fampay"},
    {"name": "Jupiter",         "slug": "jupiter-money"},
    {"name": "Slice",           "slug": "sliceit"},
    {"name": "Open Financial",  "slug": "open-financial"},
    {"name": "Yulu",            "slug": "yulu"},
    {"name": "Uni Cards",       "slug": "unicards"},
    {"name": "Zetwerk",         "slug": "zetwerk"},
    {"name": "Spinny",          "slug": "spinny"},
    {"name": "Cars24",          "slug": "cars24"},
    {"name": "Droom",           "slug": "droom"},
]

# ── Workday ATS — needs Playwright ────────────────────────────────────────────
WORKDAY_COMPANIES = [
    {"name": "Wipro",     "url": "https://wipro.wd3.myworkdayjobs.com/wiprojobs"},
    {"name": "HCL",       "url": "https://hcltech.wd3.myworkdayjobs.com/HCLTech"},
    {"name": "Cognizant", "url": "https://cognizant.wd1.myworkdayjobs.com/Cognizant_Careers"},
    {"name": "Capgemini", "url": "https://capgemini.wd3.myworkdayjobs.com/INDIA_EXTERNAL_CAREERS"},
    {"name": "Accenture", "url": "https://accenture.wd103.myworkdayjobs.com/AccentureCareers"},
    {"name": "Deloitte",  "url": "https://deloitte.wd1.myworkdayjobs.com/Deloitte_Careers"},
    {"name": "PwC",       "url": "https://pwc.wd3.myworkdayjobs.com/Global_Campus_Careers"},
    {"name": "EY",        "url": "https://eyglobal.wd5.myworkdayjobs.com/en-US/EY_External_Careers"},
]

# ── Custom career pages — needs Playwright ────────────────────────────────────
CUSTOM_CAREER_PAGES = [
    # NOTE: Companies already in GREENHOUSE_COMPANIES or LEVER_COMPANIES
    # are NOT duplicated here (Swiggy, Razorpay, CRED, Meesho, Groww,
    # Freshworks, Postman, Browserstack, etc.)

    # ── Global Tech Giants (with working career search pages) ─────────
    {
        "name"        : "Amazon",
        "url"         : "https://www.amazon.jobs/en/search?base_query=&loc_query=India",
        "job_selector": ".job-tile",
        "title_sel"   : "h3.job-title",
        "loc_sel"     : ".location-and-id",
    },
    {
        "name"        : "Apple",
        "url"         : "https://jobs.apple.com/en-in/search",
        "job_selector": "tbody tr",
        "title_sel"   : "a.table--advanced-search__title",
        "loc_sel"     : "td[class*='table--advanced-search__location']",
    },
    {
        "name"        : "Netflix",
        "url"         : "https://jobs.netflix.com/search?location=India",
        "job_selector": "div[class*='css-']",
        "title_sel"   : "span[class*='title']",
        "loc_sel"     : "span[class*='location']",
    },

    # ── Indian IT Giants ──────────────────────────────────────────────
    {
        "name"        : "TCS",
        "url"         : "https://www.tcs.com/careers/india",
        "job_selector": ".job-list-item",
        "title_sel"   : ".job-title",
        "loc_sel"     : ".job-location",
    },
    {
        "name"        : "Infosys",
        "url"         : "https://career.infosys.com/joblist",
        "job_selector": ".job-list-item",
        "title_sel"   : ".job-title",
        "loc_sel"     : ".job-location",
    },
    {
        "name"        : "Cognizant",
        "url"         : "https://careers.cognizant.com/global/en/search-results",
        "job_selector": "li[class*='jobs-list-item']",
        "title_sel"   : "a[class*='job-title']",
        "loc_sel"     : "span[class*='job-location']",
    },
    {
        "name"        : "Tech Mahindra",
        "url"         : "https://careers.techmahindra.com/ListOfJobs",
        "job_selector": ".job-list-item",
        "title_sel"   : ".job-title",
        "loc_sel"     : ".job-location",
    },

    # ── Indian Product Companies (NOT in Greenhouse/Lever) ────────────
    {
        "name"        : "Flipkart",
        "url"         : "https://www.flipkartcareers.com/#!/joblist",
        "job_selector": ".job-listing-row",
        "title_sel"   : ".job-title",
        "loc_sel"     : ".job-location",
    },
    {
        "name"        : "Zomato",
        "url"         : "https://www.zomato.com/careers",
        "job_selector": "[class*='jobCard']",
        "title_sel"   : "[class*='jobTitle']",
        "loc_sel"     : "[class*='location']",
    },
    {
        "name"        : "PhonePe",
        "url"         : "https://www.phonepe.com/careers/job-openings/",
        "job_selector": ".job-card",
        "title_sel"   : "h3",
        "loc_sel"     : ".location",
    },
    {
        "name"        : "Paytm",
        "url"         : "https://paytm.com/about-us/jobs/",
        "job_selector": "[class*='job']",
        "title_sel"   : "h3",
        "loc_sel"     : "[class*='location']",
    },
    {
        "name"        : "Zerodha",
        "url"         : "https://zerodha.com/careers/",
        "job_selector": "ul.active li",
        "title_sel"   : "a",
        "loc_sel"     : "span",
    },
    {
        "name"        : "MakeMyTrip",
        "url"         : "https://careers.makemytrip.com/",
        "job_selector": ".job-card",
        "title_sel"   : "h3",
        "loc_sel"     : ".location",
    },

    # ── Global Tech (India offices) ───────────────────────────────────
    {
        "name"        : "SAP",
        "url"         : "https://jobs.sap.com/search/?createNewAlert=false&q=&locationsearch=India",
        "job_selector": ".js-view-job",
        "title_sel"   : "h3.jobTitle",
        "loc_sel"     : "span[class*='jobLocation']",
    },
    {
        "name"        : "Adobe",
        "url"         : "https://careers.adobe.com/us/en/search-results?keywords=&location=India",
        "job_selector": "li[class*='jobs-list-item']",
        "title_sel"   : "a[class*='job-title']",
        "loc_sel"     : "span[class*='job-location']",
    },
    {
        "name"        : "Cisco",
        "url"         : "https://jobs.cisco.com/jobs/SearchJobs/?21178=%5B169482%5D&21178_format=6020&listFilterMode=1",
        "job_selector": ".result",
        "title_sel"   : "h2 a",
        "loc_sel"     : ".jobLocation",
    },
    {
        "name"        : "Zoho",
        "url"         : "https://careers.zohocorp.com/jobs/Careers",
        "job_selector": ".job-listing",
        "title_sel"   : "h3",
        "loc_sel"     : ".location",
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# LANGGRAPH STATE
# ══════════════════════════════════════════════════════════════════════════════

class MNCState(TypedDict):
    job_title         : str
    skills            : List[str]
    search_keywords   : List[str]
    greenhouse_jobs   : List[dict]
    lever_jobs        : List[dict]
    workday_jobs      : List[dict]
    custom_page_jobs  : List[dict]
    all_mnc_jobs      : List[dict]
    saved_count       : int
    error             : Optional[str]


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def clean_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r'<[^>]+>', '', text or '').strip()


def build_job(title, company, location, source,
              url, description, job_type="full-time") -> dict:
    """Build a standard job dict."""
    return {
        "id"         : str(uuid.uuid4()),
        "title"      : title[:500],
        "company"    : company[:255],
        "location"   : location[:255],
        "source"     : source,
        "url"        : url[:1000],
        "description": clean_html(description)[:5000],
        "salary"     : "",
        "job_type"   : job_type,
        "is_mnc"     : True,
        "raw_data"   : {}
    }


def keyword_match(text: str, keywords: list) -> bool:
    """Check if text contains any of the keywords.
    Splits multi-word keywords so 'Software Developer' matches
    text containing 'software' OR 'developer'.
    """
    text_lower = text.lower()
    for kw in keywords:
        # Split multi-word keywords into individual words
        words = [w.strip().lower() for w in kw.split() if len(w.strip()) >= 2]
        if any(w in text_lower for w in words):
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1 — GREENHOUSE API (free, no key)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_greenhouse_node(state: MNCState) -> MNCState:
    """Fetch jobs from all Greenhouse ATS companies."""
    keywords = [state["job_title"]] + state.get("search_keywords", []) + state["skills"][:3]
    all_jobs = []

    print(f"\n🌱 Fetching Greenhouse ATS companies...")

    for company in GREENHOUSE_COMPANIES:
        try:
            res = httpx.get(
                f"https://boards-api.greenhouse.io/v1/boards"
                f"/{company['token']}/jobs",
                params={"content": "true"},
                timeout=15
            )
            jobs = res.json().get("jobs", [])
            matched = []

            for j in jobs:
                title = j.get("title", "")
                desc  = j.get("content", "")
                if keyword_match(title + " " + desc, keywords):
                    matched.append(build_job(
                        title     = title,
                        company   = company["name"],
                        location  = j.get("location", {}).get("name", "India"),
                        source    = "greenhouse_api",
                        url       = j.get("absolute_url", ""),
                        description = desc
                    ))

            all_jobs.extend(matched)
            print(f"   ✅ {company['name']:20s}: {len(matched)} jobs")
            time.sleep(0.5)

        except Exception as e:
            print(f"   ⚠️  {company['name']}: {e}")
            continue

    print(f"   📦 Greenhouse total: {len(all_jobs)} jobs")
    return {**state, "greenhouse_jobs": all_jobs}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2 — LEVER API (free, no key)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_lever_node(state: MNCState) -> MNCState:
    """Fetch jobs from all Lever ATS companies."""
    keywords = [state["job_title"]] + state.get("search_keywords", []) + state["skills"][:3]
    all_jobs = []

    print(f"\n⚙️  Fetching Lever ATS companies...")

    for company in LEVER_COMPANIES:
        try:
            res = httpx.get(
                f"https://api.lever.co/v0/postings/{company['slug']}",
                params={"mode": "json"},
                timeout=15
            )

            if res.status_code != 200:
                print(f"   ⚠️  {company['name']}: HTTP {res.status_code}")
                continue

            jobs    = res.json()
            matched = []

            if isinstance(jobs, list):
                for j in jobs:
                    title = j.get("text", "")
                    desc  = j.get("descriptionPlain", "") or ""
                    cats  = j.get("categories", {})

                    # Include job if it matches keywords
                    if keyword_match(title + " " + desc, keywords):
                        matched.append(build_job(
                            title       = title,
                            company     = company["name"],
                            location    = cats.get("location", "India"),
                            source      = "lever_api",
                            url         = j.get("hostedUrl", ""),
                            description = desc,
                            job_type    = cats.get("commitment", "full-time")
                        ))

                all_jobs.extend(matched)
                print(f"   ✅ {company['name']:20s}: {len(jobs)} total, {len(matched)} matched")
            else:
                print(f"   ⚠️  {company['name']}: Invalid response format")
            time.sleep(0.5)

        except Exception as e:
            print(f"   ⚠️  {company['name']}: {e}")
            continue

    print(f"   📦 Lever total: {len(all_jobs)} jobs")
    return {**state, "lever_jobs": all_jobs}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3 — WORKDAY PAGES (Playwright)
# ══════════════════════════════════════════════════════════════════════════════

def _scrape_workday_page_sync(company: dict,
                              keyword: str) -> list:
    """Sync Workday scraper — runs in thread pool for Windows compatibility."""
    jobs_found = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            try:
                # Search with keyword in URL
                url = f"{company['url']}?q={keyword.replace(' ', '+')}"
                page.goto(url, timeout=30000,
                          wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # Workday standard selectors
                selectors = [
                    "[data-automation-id='jobTitle']",
                    "li[class*='css-1q2dra3']",
                    "[class*='jobResult']",
                    "li[class*='job']",
                    ".gwt-Label",
                ]

                items = []
                for sel in selectors:
                    items = page.query_selector_all(sel)
                    if items:
                        break

                for item in items[:20]:
                    try:
                        text     = item.inner_text()
                        link_el  = item.query_selector("a")
                        href     = ""
                        if link_el:
                            href = link_el.get_attribute("href") or ""
                            if href and not href.startswith("http"):
                                base = company["url"].split("/")[2]
                                href = f"https://{base}{href}"

                        if text.strip():
                            jobs_found.append(build_job(
                                title       = text.split("\n")[0][:200],
                                company     = company["name"],
                                location    = "India",
                                source      = "workday_scraper",
                                url         = href or company["url"],
                                description = text[:2000]
                            ))
                    except Exception:
                        continue

                # AI fallback if no structured items
                if not jobs_found:
                    page_text = page.evaluate("document.body.innerText")
                    if page_text and len(page_text) > 300:
                        jobs_found = extract_with_ai(
                            page_text[:3000],
                            company["name"],
                            company["url"],
                            keyword
                        )

            except Exception as e:
                print(f"   ⚠️  {company['name']} Workday error: {e}")

            finally:
                browser.close()

    except Exception as e:
        print(f"   ⚠️  {company['name']} Workday launch: {e}")

    return jobs_found


async def scrape_workday_page(company: dict, keyword: str) -> list:
    """Async wrapper — runs sync Playwright in a thread pool."""
    return await asyncio.to_thread(_scrape_workday_page_sync, company, keyword)


async def scrape_all_workday(keyword: str) -> list:
    """Scrape all Workday companies concurrently."""
    print(f"\n⚡ Scraping Workday ATS companies...")

    sem   = asyncio.Semaphore(2)
    all_jobs = []

    async def scrape_limited(company):
        async with sem:
            jobs = await scrape_workday_page(company, keyword)
            await asyncio.sleep(2)
            print(f"   ✅ {company['name']:20s}: {len(jobs)} jobs")
            return jobs

    tasks   = [scrape_limited(c) for c in WORKDAY_COMPANIES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)

    print(f"   📦 Workday total: {len(all_jobs)} jobs")
    return all_jobs


async def fetch_workday_node(state: MNCState) -> MNCState:
    """Node wrapper for Workday scraping."""
    jobs = await scrape_all_workday(state["job_title"])
    return {**state, "workday_jobs": jobs}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4 — CUSTOM CAREER PAGES (Playwright)
# ══════════════════════════════════════════════════════════════════════════════

def _inject_keyword_into_url(url: str, keyword: str) -> str:
    """Inject the user's keyword into a career page URL.
    Handles common patterns like ?q=, ?search=, ?keywords=, ?base_query=
    """
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)

    # Common search parameter names used by career sites
    search_params = ["q", "query", "search", "keyword", "keywords",
                     "base_query", "searchText", "term"]

    injected = False
    for sp in search_params:
        if sp in params:
            params[sp] = [keyword]
            injected = True
            break

    # If no existing param found, append ?q=keyword
    if not injected:
        params["q"] = [keyword]

    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _scrape_custom_page_sync(company: dict, keyword: str) -> list:
    """Sync Playwright scraper — runs in a thread pool to avoid
    Windows uvicorn event-loop subprocess limitation.
    """
    jobs_found = []
    keywords = [k.strip().lower() for k in keyword.split() if len(k.strip()) >= 2]

    # Inject the user's keyword into the career page URL
    career_url = _inject_keyword_into_url(company["url"], keyword)
    print(f"      🔗 {company['name']}: {career_url[:100]}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            try:
                page.goto(career_url, timeout=45000,
                          wait_until="domcontentloaded")
                # Wait for JS-heavy SPAs to render
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                page.wait_for_timeout(3000)

                # ── Strategy 1: Try search box if available ───────────────────
                search_selectors = [
                    "input[placeholder*='earch']",
                    "input[type='search']",
                    "input[name='q']",
                    "input[name='query']",
                    "input[name='keyword']",
                    "input[aria-label*='earch']",
                    "#searchBox", ".search-input",
                    "input[id*='search']",
                ]
                for sel in search_selectors:
                    try:
                        search_box = page.query_selector(sel)
                        if search_box and search_box.is_visible():
                            search_box.fill(keyword)
                            page.keyboard.press("Enter")
                            page.wait_for_timeout(3000)
                            break
                    except Exception:
                        continue

                # ── Strategy 2: Company-specific selectors ────────────────────
                items = page.query_selector_all(
                    company.get("job_selector", ".job-NONEXISTENT")
                )

                if items:
                    for item in items[:30]:
                        try:
                            title    = ""
                            title_el = item.query_selector(
                                company.get("title_sel", "h3")
                            )
                            if title_el:
                                title = title_el.inner_text().strip()
                            if not title:
                                title = item.inner_text().split("\n")[0].strip()

                            location    = "India"
                            location_el = item.query_selector(
                                company.get("loc_sel", "[class*='location']")
                            )
                            if location_el:
                                location = location_el.inner_text().strip()

                            href    = ""
                            link_el = item.query_selector("a")
                            if link_el:
                                href = link_el.get_attribute("href") or ""
                                if href and not href.startswith("http"):
                                    base = company["url"].split("/")[0] + "//" + company["url"].split("/")[2]
                                    href = base + (href if href.startswith("/") else "/" + href)

                            if title and any(k in title.lower() for k in keywords):
                                jobs_found.append(build_job(
                                    title       = title,
                                    company     = company["name"],
                                    location    = location,
                                    source      = "custom_career_page",
                                    url         = href or company["url"],
                                    description = item.inner_text()[:2000]
                                ))
                        except Exception:
                            continue

                # ── Strategy 3: Generic link extraction ───────────────────────
                if not jobs_found:
                    all_links = page.evaluate("""() => {
                        const results = [];
                        const links = document.querySelectorAll('a');
                        links.forEach(a => {
                            const text = (a.innerText || '').trim();
                            const href = a.href || '';
                            const parent = a.closest('li, tr, div, article');
                            const context = parent ? (parent.innerText || '').trim().substring(0, 300) : text;
                            if (text.length > 5 && text.length < 200 && href) {
                                results.push({title: text, href: href, context: context});
                            }
                        });
                        return results;
                    }""")

                    # Job-like URL patterns — match actual job posting URLs, not nav pages
                    job_url_re = re.compile(
                        r'/(?:jobs?|positions?|openings?|roles?|vacancies|opportunities?|apply)'
                        r'(?:/[\w-]+|\?|#|$)',
                        re.IGNORECASE
                    )

                    skip_words = ["login", "sign in", "sign up", "cookie", "privacy",
                                  "about us", "contact us", "blog", "news", "faq",
                                  "help", "terms", "signup", "pricing", "products",
                                  "why work", "benefits", "perks", "career growth",
                                  "who we hire", "entry-level", "military", "veteran",
                                  "search results", "skip to", "careers home",
                                  "home", "menu", "navigation", "footer"]

                    seen_titles = set()
                    for link in all_links:
                        title = link.get("title", "").strip()
                        href  = link.get("href", "")
                        ctx   = link.get("context", "").lower()

                        if not title or title in seen_titles or len(title) < 8:
                            continue

                        title_lower = title.lower()

                        # Skip obvious nav/footer links
                        if any(sw in title_lower for sw in skip_words):
                            continue

                        href_lower = href.lower()
                        is_job_url = bool(job_url_re.search(href_lower))
                        has_keyword = any(k in title_lower or k in ctx for k in keywords)

                        if has_keyword or is_job_url:
                            seen_titles.add(title)
                            jobs_found.append(build_job(
                                title       = title,
                                company     = company["name"],
                                location    = "India",
                                source      = "custom_career_page",
                                url         = href or company["url"],
                                description = link.get("context", "")
                            ))

                            if len(jobs_found) >= 25:
                                break

                # ── Strategy 4: AI fallback from raw page text ────────────────
                if not jobs_found:
                    page_text = page.evaluate("document.body.innerText")
                    if page_text and len(page_text.strip()) > 100:
                        jobs_found = extract_with_ai(
                            page_text[:4000],
                            company["name"],
                            company["url"],
                            keyword
                        )

            except Exception as e:
                print(f"   ⚠️  {company['name']}: {e}")

            finally:
                browser.close()

    except Exception as e:
        print(f"   ⚠️  {company['name']} (launch): {e}")

    return jobs_found


async def scrape_custom_page(company: dict, keyword: str) -> list:
    """Async wrapper — runs sync Playwright in a thread pool."""
    return await asyncio.to_thread(_scrape_custom_page_sync, company, keyword)


async def scrape_all_custom(keyword: str) -> list:
    """Scrape all custom career pages concurrently."""
    print(f"\n🌐 Scraping custom MNC career pages...")

    sem      = asyncio.Semaphore(2)
    all_jobs = []

    async def scrape_limited(company):
        async with sem:
            jobs = await scrape_custom_page(company, keyword)
            await asyncio.sleep(2)
            print(f"   ✅ {company['name']:20s}: {len(jobs)} jobs")
            return jobs

    tasks   = [scrape_limited(c) for c in CUSTOM_CAREER_PAGES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)

    print(f"   📦 Custom pages total: {len(all_jobs)} jobs")
    return all_jobs


async def fetch_custom_pages_node(state: MNCState) -> MNCState:
    """Node wrapper for custom career page scraping.
    Scrapes using job_title and also each user-provided search keyword (up to 10).
    """
    all_jobs = []

    # Build a deduplicated list of all search queries
    queries = [state["job_title"]]
    for kw in state.get("search_keywords", [])[:3]:
        kw = kw.strip()
        if kw and kw.lower() not in [q.lower() for q in queries]:
            queries.append(kw)

    print(f"\n🔎 Custom pages — searching with {len(queries)} keywords: {queries}")

    for idx, kw in enumerate(queries):
        print(f"\n   [{idx+1}/{len(queries)}] Keyword: '{kw}'")
        jobs = await scrape_all_custom(kw)
        all_jobs.extend(jobs)

    # Deduplicate by URL
    seen = set()
    unique = []
    for j in all_jobs:
        url = j.get("url", "")
        if url not in seen:
            seen.add(url)
            unique.append(j)

    return {**state, "custom_page_jobs": unique}


# ══════════════════════════════════════════════════════════════════════════════
# AI FALLBACK — extract jobs from raw page text
# ══════════════════════════════════════════════════════════════════════════════

def extract_with_ai(page_text: str, company: str,
                    url: str, keyword: str) -> list:
    """Use Groq to extract job listings from raw page text."""
    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Extract job listings from text. Return ONLY valid JSON array."),
        ("human", """
        Find all {keyword} related job openings in this text.
        Return JSON array:
        [{{"title": "...", "location": "...", "description": "..."}}]
        If none found return [].
        Text: {text}
        Return ONLY JSON array, no explanation.
        """)
    ])
    chain = prompt | llm | parser

    try:
        result = chain.invoke({"keyword": keyword, "text": page_text})
        jobs   = []
        if isinstance(result, list):
            for item in result:
                if item.get("title"):
                    jobs.append(build_job(
                        title       = item.get("title", ""),
                        company     = company,
                        location    = item.get("location", "India"),
                        source      = "ai_extracted",
                        url         = url,
                        description = item.get("description", "")
                    ))
        return jobs
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# NODE 5 — MERGE + DEDUPLICATE
# ══════════════════════════════════════════════════════════════════════════════

def merge_mnc_jobs_node(state: MNCState) -> MNCState:
    """Merge all MNC job sources and deduplicate by URL."""
    print(f"\n🔀 Merging all MNC jobs...")
    print(f"   Greenhouse    : {len(state['greenhouse_jobs'])}")
    print(f"   Lever         : {len(state['lever_jobs'])}")
    print(f"   Workday       : {len(state['workday_jobs'])}")
    print(f"   Custom Pages  : {len(state['custom_page_jobs'])}")

    all_jobs  = (
        state["greenhouse_jobs"] +
        state["lever_jobs"]      +
        state["workday_jobs"]    +
        state["custom_page_jobs"]
    )

    seen_urls = set()
    unique    = []

    for job in all_jobs:
        url = job.get("url", "").strip()
        if not job.get("title") or not url:
            continue
        if url not in seen_urls:
            seen_urls.add(url)
            unique.append(job)

    print(f"   ✅ After dedup: {len(all_jobs)} → {len(unique)} unique jobs")
    return {**state, "all_mnc_jobs": unique}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 6 — SAVE TO POSTGRESQL
# ══════════════════════════════════════════════════════════════════════════════

def save_mnc_jobs_node(state: MNCState) -> MNCState:
    """Save all MNC jobs to the mnc_jobs table."""
    from db.connection import get_db_connection

    jobs  = state["all_mnc_jobs"]
    print(f"\n💾 Saving {len(jobs)} MNC jobs to PostgreSQL...")

    db    = get_db_connection()
    cur   = db.cursor()
    saved = 0

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mnc_jobs (
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
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migration: ensure all columns exist
        columns_to_check = {
            "salary": "VARCHAR(255)",
            "raw_data": "JSONB",
            "scraped_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        }
        for col, col_type in columns_to_check.items():
            try:
                # Check if column exists
                cur.execute(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='mnc_jobs' AND column_name=%s
                """, (col,))
                if not cur.fetchone():
                    print(f"   🔧 Migrating: Adding {col} to mnc_jobs")
                    cur.execute(f"ALTER TABLE mnc_jobs ADD COLUMN {col} {col_type}")
                    db.commit()
            except Exception as e:
                print(f"   ⚠️ Migration error for {col}: {e}")
                db.rollback()

        db.commit()

        skipped = 0
        errors  = 0
        error_samples = []

        for job in jobs:
            try:
                cur.execute("SAVEPOINT sp")
                cur.execute("""
                    INSERT INTO mnc_jobs
                        (id, title, company, location, source,
                         url, description, salary, job_type, raw_data)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (url) DO UPDATE SET
                        title = EXCLUDED.title,
                        company = EXCLUDED.company,
                        scraped_at = CURRENT_TIMESTAMP
                """, (
                    str(uuid.uuid4()),
                    job.get("title",  "")[:500],
                    job.get("company","")[:255],
                    job.get("location","")[:255],
                    job.get("source", "")[:100],
                    job.get("url",    "")[:1000],
                    job.get("description","")[:5000],
                    job.get("salary", "")[:255],
                    job.get("job_type","")[:100],
                    json.dumps({"is_mnc": True,
                                "source": job.get("source","")})
                ))
                cur.execute("RELEASE SAVEPOINT sp")
                saved += 1
            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                errors += 1
                if len(error_samples) < 3:
                    error_samples.append(f"{job.get('title','')[:40]}: {str(e)[:80]}")
                continue

        db.commit()

        if error_samples:
            print(f"   ⚠️  Sample errors:")
            for es in error_samples:
                print(f"      {es}")

        print(f"   ✅ Saved {saved} MNC jobs ({errors} errors)")

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

def summary_node(state: MNCState) -> MNCState:
    """Print final summary."""
    jobs = state["all_mnc_jobs"]

    print(f"\n{'='*55}")
    print(f"🏢 MNC Career Agent Summary")
    print(f"{'='*55}")
    print(f"   Keyword       : {state['job_title']}")
    print(f"   Greenhouse    : {len(state['greenhouse_jobs'])}")
    print(f"   Lever         : {len(state['lever_jobs'])}")
    print(f"   Workday       : {len(state['workday_jobs'])}")
    print(f"   Custom Pages  : {len(state['custom_page_jobs'])}")
    print(f"   Total unique  : {len(jobs)}")
    print(f"   Saved to DB   : {state['saved_count']}")

    # Source breakdown
    sources = {}
    for j in jobs:
        s = j.get("source","unknown")
        sources[s] = sources.get(s, 0) + 1

    print(f"\n   By source:")
    for s, c in sorted(sources.items(), key=lambda x: x[1], reverse=True):
        print(f"      {s:30s}: {c}")

    print(f"\n   Top matches:")
    for job in jobs[:5]:
        print(f"   🏢 {job['title']} @ {job['company']}")
        print(f"      {job['url']}")

    print(f"{'='*55}\n")
    return state


# ══════════════════════════════════════════════════════════════════════════════
# BUILD LANGGRAPH PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def build_mnc_graph():
    """Build LangGraph pipeline for MNC career fetching."""
    graph = StateGraph(MNCState)

    graph.add_node("greenhouse"    , fetch_greenhouse_node)
    graph.add_node("custom_pages"  , fetch_custom_pages_node)
    graph.add_node("merge"         , merge_mnc_jobs_node)
    graph.add_node("save"          , save_mnc_jobs_node)
    graph.add_node("summary"       , summary_node)

    graph.set_entry_point("greenhouse")
    graph.add_edge("greenhouse"  , "custom_pages")
    graph.add_edge("custom_pages", "merge")
    graph.add_edge("merge"       , "save")
    graph.add_edge("save"        , "summary")
    graph.add_edge("summary"     , END)

    return graph.compile()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION — CALL THIS FROM OTHER AGENTS
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_mnc_jobs(parsed_resume: dict) -> list:
    """
    Full LangGraph pipeline:
    1. Fetch from Greenhouse ATS API  (free)
    2. Scrape custom career pages     (Playwright)
    3. Merge + deduplicate
    4. Save to PostgreSQL

    Returns list of all unique MNC jobs found.
    """
    job_title = ""
    if parsed_resume.get("job_titles"):
        job_title = parsed_resume["job_titles"][0]
    else:
        skills    = parsed_resume.get("skills", [])
        job_title = f"{skills[0]} developer" if skills else "software engineer"

    skills          = parsed_resume.get("skills", [])
    search_keywords = parsed_resume.get("search_keywords", [])

    pipeline    = build_mnc_graph()
    final_state = await pipeline.ainvoke({
        "job_title"       : job_title,
        "skills"          : skills,
        "search_keywords" : search_keywords,
        "greenhouse_jobs" : [],
        "lever_jobs"      : [],
        "workday_jobs"    : [],
        "custom_page_jobs": [],
        "all_mnc_jobs"    : [],
        "saved_count"     : 0,
        "error"           : None
    })

    return final_state["all_mnc_jobs"]