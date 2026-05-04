import os
import re
import json
import uuid
import time
import asyncio
from typing import TypedDict, List, Optional
from dotenv import load_dotenv

import httpx
from ddgs import DDGS
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
# LANGGRAPH STATE
# ══════════════════════════════════════════════════════════════════════════════

class ContactState(TypedDict):
    job             : dict           # single job from jobs/local_jobs table
    company         : str
    domain          : str
    company_phone   : str            # found company phone
    hr_contacts     : List[dict]     # found HR / recruiter contacts
    employee_contacts: List[dict]    # found current employees
    all_contacts    : List[dict]     # merged all contacts
    saved_count     : int
    error           : Optional[str]


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def safe_ddg_search(query: str, max_results: int = 5) -> list:
    """DuckDuckGo search with retry."""
    for attempt in range(3):
        try:
            with DDGS() as ddgs:
                return ddgs.text(query, max_results=max_results) or []
        except Exception as e:
            time.sleep((attempt + 1) * 3)
    return []


def extract_domain_from_company(company_name: str,
                                company_url: str = "") -> str:
    """Extract clean domain from company URL or guess from name."""
    ignore_domains = [
        "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
        "naukri.com", "foundit.in", "monster.com", "simplyhired.com",
        "workday.com", "myworkdayjobs.com", "lever.co", "greenhouse.io", "ashbyhq.com"
    ]

    from urllib.parse import urlparse

    def get_host(u: str) -> str:
        if not u.strip().startswith('http'):
            u = 'http://' + u.strip()
        netloc = urlparse(u).netloc
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        return netloc.lower()

    # Try from URL first
    if company_url:
        extracted = get_host(company_url)
        if extracted and not any(ignore in extracted for ignore in ignore_domains):
            return extracted

    # Try finding real domain via DDG search
    try:
        results = safe_ddg_search(f'{company_name} official website', max_results=3)
        for r in results:
            href = r.get("href", "")
            if href:
                extracted = get_host(href)
                if extracted and not any(ignore in extracted for ignore in ignore_domains):
                    return extracted
    except Exception:
        pass

    # Final fallback if search fails
    clean = re.sub(r'[^a-zA-Z0-9]', '', company_name.lower())
    return f"{clean}.com"


def extract_linkedin_username(url: str) -> str:
    """Extract LinkedIn username from profile URL."""
    match = re.search(r'linkedin\.com/in/([a-zA-Z0-9\-]+)', url)
    return match.group(1) if match else ""


def is_valid_email(email: str) -> bool:
    """Basic email format validation."""
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1 — EXTRACT DOMAIN
# ══════════════════════════════════════════════════════════════════════════════

def extract_domain_node(state: ContactState) -> ContactState:
    """Extract company domain from job data."""
    job     = state["job"]
    company = job.get("company", "").strip()
    url     = job.get("url", "")

    domain = extract_domain_from_company(company, url)

    # --- Find Phone Number ---
    phone = ""
    try:
        results = safe_ddg_search(f'{company} "phone number" OR "contact number"', max_results=3)
        for r in results:
            match = re.search(r'(?:\+?\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}', r.get("body", ""))
            if match and len(match.group(0).strip()) >= 8:
                phone = match.group(0).strip()
                break
    except Exception:
        pass

    print(f"\n{'='*55}")
    print(f"🔍 Contact Finder — {company}")
    print(f"   Domain  : {domain}")
    print(f"   Phone   : {phone or 'Not found'}")
    print(f"{'='*55}")

    return {**state, "company": company, "domain": domain, "company_phone": phone}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2 — FIND HR EMAILS (Hunter.io + Snov.io + Fallback)
# ══════════════════════════════════════════════════════════════════════════════

def find_hr_emails_node(state: ContactState) -> ContactState:
    """
    Find HR / Recruiter emails using:
    Layer 1 → Check own DB cache (free)
    Layer 2 → Hunter.io API (25 free/month)
    Layer 3 → Snov.io API (150 free/month)
    Layer 4 → Scrape company website (free)
    Layer 5 → Email pattern guesser + verifier (free)
    """
    domain   = state["domain"]
    company  = state["company"]
    hr_contacts = []

    print(f"\n📧 Finding HR emails for {company}...")

    # ── Layer 1: Check DB cache ───────────────────────────────────────────────
    cached = get_cached_contacts(company, "hr")
    if cached:
        print(f"   ✅ Layer 1 (DB cache): {len(cached)} HR contacts found")
        return {**state, "hr_contacts": cached}

    # ── Layer 2: Hunter.io ────────────────────────────────────────────────────
    hunter_key = os.getenv("HUNTER_API_KEY")
    if hunter_key:
        try:
            res = httpx.get(
                "https://api.hunter.io/v2/domain-search",
                params={
                    "domain"    : domain,
                    "api_key"   : hunter_key,
                    "limit"     : 10,
                    "type"      : "personal"
                },
                timeout=15
            )
            data   = res.json().get("data", {})
            emails = data.get("emails", [])

            hr_keywords = ["hr", "recruit", "talent", "hiring",
                           "people", "human", "career", "staff"]

            for e in emails:
                position = e.get("position", "").lower()
                if any(kw in position for kw in hr_keywords):
                    hr_contacts.append({
                        "id"          : str(uuid.uuid4()),
                        "name"        : f"{e.get('first_name','')} {e.get('last_name','')}".strip(),
                        "email"       : e.get("value", ""),
                        "role"        : e.get("position", "HR"),
                        "company"     : company,
                        "domain"      : domain,
                        "linkedin_url": e.get("linkedin", ""),
                        "verified"    : e.get("confidence", 0) > 70,
                        "found_via"   : "hunter.io"
                    })

            print(f"   ✅ Layer 2 (Hunter.io): {len(hr_contacts)} HR contacts")

        except Exception as e:
            print(f"   ⚠️  Hunter.io error: {e}")

    # ── Layer 3: Snov.io ──────────────────────────────────────────────────────
    if not hr_contacts:
        snov_user = os.getenv("SNOV_USER_ID")
        snov_sec  = os.getenv("SNOV_SECRET")
        if snov_user and snov_sec:
            try:
                # Get Snov.io access token
                token_res = httpx.post(
                    "https://api.snov.io/v1/oauth/access_token",
                    data={
                        "grant_type"   : "client_credentials",
                        "client_id"    : snov_user,
                        "client_secret": snov_sec
                    },
                    timeout=15
                )
                token = token_res.json().get("access_token")

                if token:
                    res = httpx.post(
                        "https://api.snov.io/v1/get-domain-emails-with-info",
                        data={
                            "access_token": token,
                            "domain"      : domain,
                            "type"        : "personal",
                            "limit"       : 10
                        },
                        timeout=15
                    )
                    emails = res.json().get("emails", [])

                    for e in emails:
                        name = e.get("name", "")
                        pos  = e.get("currentJob", [{}])
                        role = pos[0].get("position","") if pos else ""

                        hr_keywords = ["hr","recruit","talent","people"]
                        if any(kw in role.lower() for kw in hr_keywords):
                            hr_contacts.append({
                                "id"          : str(uuid.uuid4()),
                                "name"        : name,
                                "email"       : e.get("email",""),
                                "role"        : role or "HR",
                                "company"     : company,
                                "domain"      : domain,
                                "linkedin_url": "",
                                "verified"    : True,
                                "found_via"   : "snov.io"
                            })

                    print(f"   ✅ Layer 3 (Snov.io): {len(hr_contacts)} contacts")

            except Exception as e:
                print(f"   ⚠️  Snov.io error: {e}")

    # ── Layer 4: Scrape company website for emails ────────────────────────────
    if not hr_contacts:
        website_emails = scrape_emails_from_website(domain)
        for email in website_emails:
            hr_contacts.append({
                "id"          : str(uuid.uuid4()),
                "name"        : "",
                "email"       : email,
                "role"        : "Contact",
                "company"     : company,
                "domain"      : domain,
                "linkedin_url": "",
                "verified"    : False,
                "found_via"   : "website_scrape"
            })
        print(f"   ✅ Layer 4 (Website): {len(hr_contacts)} emails")

    # ── Layer 5: Email pattern guesser ────────────────────────────────────────
    if not hr_contacts:
        guessed = guess_hr_email(domain, company)
        if guessed:
            hr_contacts.append({
                "id"          : str(uuid.uuid4()),
                "name"        : "HR Team",
                "email"       : guessed,
                "role"        : "HR",
                "company"     : company,
                "domain"      : domain,
                "linkedin_url": "",
                "verified"    : False,
                "found_via"   : "pattern_guess"
            })
        print(f"   ✅ Layer 5 (Pattern): {1 if guessed else 0} emails")

    # Filter valid emails only
    hr_contacts = [c for c in hr_contacts if is_valid_email(c.get("email",""))]
    print(f"   📦 HR contacts total: {len(hr_contacts)}")

    return {**state, "hr_contacts": hr_contacts}


def scrape_emails_from_website(domain: str) -> list:
    """Scrape emails from company contact/about page."""
    emails_found = []
    pages_to_try = [
        f"https://{domain}/contact",
        f"https://{domain}/contact-us",
        f"https://{domain}/about",
        f"https://www.{domain}/contact",
    ]

    for url in pages_to_try:
        try:
            res  = httpx.get(url, timeout=10,
                             follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            text = res.text
            emails = re.findall(
                r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
                text
            )
            # Filter out generic/no-reply emails
            skip = ["noreply","no-reply","support","info",
                    "admin","webmaster","example"]
            emails = [e for e in emails
                      if not any(s in e.lower() for s in skip)]

            if emails:
                emails_found.extend(list(set(emails))[:3])
                break

        except Exception:
            continue

    return emails_found[:3]


def guess_hr_email(domain: str, company: str) -> str:
    """Guess common HR email patterns and verify."""
    hunter_key = os.getenv("HUNTER_API_KEY")
    patterns   = [
        f"hr@{domain}",
        f"careers@{domain}",
        f"recruitment@{domain}",
        f"hiring@{domain}",
        f"talent@{domain}",
        f"jobs@{domain}",
    ]

    for email in patterns:
        if not hunter_key:
            return email  # return first guess if no verifier

        try:
            res = httpx.get(
                "https://api.hunter.io/v2/email-verifier",
                params={"email": email, "api_key": hunter_key},
                timeout=10
            )
            status = res.json().get("data", {}).get("status", "")
            if status in ["valid", "accept_all"]:
                return email
        except Exception:
            continue

    return patterns[0]  # return hr@ as last resort


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3 — FIND EMPLOYEES ON LINKEDIN
# ══════════════════════════════════════════════════════════════════════════════

def find_employees_node(state: ContactState) -> ContactState:
    """
    Find current employees at the company using:
    Layer 1 → DB cache (free)
    Layer 2 → Google-cached LinkedIn search via DuckDuckGo (free)
    Layer 3 → Proxycurl API (paid but accurate)
    """
    company   = state["company"]
    job_title = state["job"].get("title", "")
    employees = []

    print(f"\n👥 Finding employees at {company}...")

    # ── Layer 1: DB cache ─────────────────────────────────────────────────────
    cached = get_cached_contacts(company, "employee")
    if cached:
        print(f"   ✅ Layer 1 (cache): {len(cached)} employees found")
        return {**state, "employee_contacts": cached}

    # ── Layer 2: DuckDuckGo LinkedIn search (free) ────────────────────────────
    queries = [
        f'site:linkedin.com/in "{company}" "{job_title}"',
        f'site:linkedin.com/in "{company}" "software engineer"',
        f'site:linkedin.com/in "{company}" "developer"',
    ]

    seen_urls = set()
    for query in queries:
        results = safe_ddg_search(query, max_results=5)
        time.sleep(2)

        for r in results:
            url = r.get("href", "")
            if "linkedin.com/in/" not in url:
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Extract name from title
            title_text = r.get("title", "")
            name       = title_text.split("-")[0].strip()
            role       = title_text.split("-")[1].strip() \
                         if "-" in title_text else "Employee"

            employees.append({
                "id"          : str(uuid.uuid4()),
                "name"        : name,
                "email"       : "",       # will fill in next node
                "role"        : role,
                "company"     : company,
                "domain"      : state["domain"],
                "linkedin_url": url,
                "verified"    : False,
                "found_via"   : "linkedin_ddg"
            })

        if len(employees) >= 5:
            break

    print(f"   ✅ Layer 2 (DDG LinkedIn): {len(employees)} employees")

    # ── Layer 3: Proxycurl (optional, paid) ───────────────────────────────────
    proxycurl_key = os.getenv("PROXYCURL_API_KEY")
    if not employees and proxycurl_key:
        try:
            res = httpx.get(
                "https://nubela.co/proxycurl/api/linkedin/company/employees",
                params={
                    "url"              : f"https://linkedin.com/company/{company.lower().replace(' ','-')}",
                    "role_search"      : job_title,
                    "country"         : "IN",
                    "resolve_numeric_id": "true"
                },
                headers={"Authorization": f"Bearer {proxycurl_key}"},
                timeout=20
            )
            data = res.json()
            for emp in data.get("employees", [])[:5]:
                employees.append({
                    "id"          : str(uuid.uuid4()),
                    "name"        : emp.get("name", ""),
                    "email"       : "",
                    "role"        : emp.get("title", "Employee"),
                    "company"     : company,
                    "domain"      : state["domain"],
                    "linkedin_url": emp.get("profile_url", ""),
                    "verified"    : True,
                    "found_via"   : "proxycurl"
                })
            print(f"   ✅ Layer 3 (Proxycurl): {len(employees)} employees")

        except Exception as e:
            print(f"   ⚠️  Proxycurl error: {e}")

    print(f"   📦 Employees total: {len(employees)}")
    return {**state, "employee_contacts": employees}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4 — FIND EMPLOYEE EMAILS
# ══════════════════════════════════════════════════════════════════════════════

def find_employee_emails_node(state: ContactState) -> ContactState:
    """
    Find email addresses for each employee found.
    Uses email pattern guessing + Hunter.io verification.
    """
    employees = state["employee_contacts"]
    domain    = state["domain"]

    if not employees:
        return state

    print(f"\n📨 Finding emails for {len(employees)} employees...")
    hunter_key = os.getenv("HUNTER_API_KEY")

    for emp in employees:
        if emp.get("email"):
            continue  # already has email

        name  = emp.get("name", "")
        parts = name.lower().split()
        if len(parts) < 2:
            continue

        first = parts[0]
        last  = parts[-1]

        # Common email patterns
        patterns = [
            f"{first}.{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{first[0]}{last}@{domain}",
            f"{first}.{last[0]}@{domain}",
            f"{first}@{domain}",
        ]

        email_found = ""

        # Verify with Hunter.io if key available
        if hunter_key:
            for pattern in patterns:
                try:
                    res = httpx.get(
                        "https://api.hunter.io/v2/email-verifier",
                        params={
                            "email"  : pattern,
                            "api_key": hunter_key
                        },
                        timeout=10
                    )
                    status = res.json().get("data",{}).get("status","")
                    if status in ["valid", "accept_all"]:
                        email_found = pattern
                        emp["verified"] = True
                        break
                    time.sleep(0.5)
                except Exception:
                    continue
        else:
            # No verifier — use first pattern as best guess
            email_found = patterns[0]

        if email_found:
            emp["email"] = email_found
            print(f"   ✅ {emp['name']:25s} → {email_found}")

    return {**state, "employee_contacts": employees}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 5 — USE AI TO ENRICH CONTACTS
# ══════════════════════════════════════════════════════════════════════════════

def enrich_contacts_node(state: ContactState) -> ContactState:
    """
    Use Groq to clean, deduplicate and enrich
    contact data — fix names, normalize roles etc.
    """
    all_contacts = state["hr_contacts"] + state["employee_contacts"]

    if not all_contacts:
        print("   ⚠️  No contacts to enrich")
        return {**state, "all_contacts": []}

    print(f"\n🤖 Enriching {len(all_contacts)} contacts with AI...")

    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Clean and normalize contact data. Return ONLY valid JSON."),
        ("human", """
        Clean this list of contacts for {company}.
        Fix names (proper case), normalize roles, remove duplicates.
        Return JSON array:
        [{{
          "name"        : "Full Name",
          "email"       : "email@domain.com",
          "role"        : "normalized role",
          "linkedin_url": "url or empty",
          "priority"    : 1
        }}]

        Priority: 1=HR/Recruiter (highest), 2=Manager, 3=Employee

        Contacts: {contacts}

        Return ONLY JSON array.
        """)
    ])
    chain = prompt | llm | parser

    try:
        enriched = chain.invoke({
            "company" : state["company"],
            "contacts": json.dumps([
                {k: v for k, v in c.items()
                 if k in ["name","email","role","linkedin_url"]}
                for c in all_contacts[:10]
            ])
        })

        # Merge enriched data back
        if isinstance(enriched, list):
            for i, contact in enumerate(all_contacts[:len(enriched)]):
                if i < len(enriched):
                    contact["name"]         = enriched[i].get("name", contact["name"])
                    contact["role"]         = enriched[i].get("role", contact["role"])
                    contact["priority"]     = enriched[i].get("priority", 3)

        print(f"   ✅ Contacts enriched")

    except Exception as e:
        print(f"   ⚠️  Enrichment failed: {e}")
        for c in all_contacts:
            c["priority"] = 1 if any(
                kw in c.get("role","").lower()
                for kw in ["hr","recruit","talent"]
            ) else 3

    # Sort by priority
    all_contacts.sort(key=lambda x: x.get("priority", 3))

    return {**state, "all_contacts": all_contacts}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 6 — SAVE TO POSTGRESQL
# ══════════════════════════════════════════════════════════════════════════════

def save_contacts_node(state: ContactState) -> ContactState:
    """Save all contacts to global_contacts table."""
    from db.connection import get_db_connection

    contacts = state["all_contacts"]
    if not contacts:
        print("   ⚠️  No contacts to save")
        return {**state, "saved_count": 0}

    print(f"\n💾 Saving {len(contacts)} contacts to PostgreSQL...")

    db    = get_db_connection()
    cur   = db.cursor()
    saved = 0

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS global_contacts (
                id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255),
                email VARCHAR(255) UNIQUE,
                company VARCHAR(255),
                domain VARCHAR(255),
                linkedin_url VARCHAR(500),
                role VARCHAR(100),
                verified BOOLEAN DEFAULT FALSE,
                found_via VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for c in contacts:
            email = c.get("email", "")
            if not email or not is_valid_email(email):
                continue

            try:
                cur.execute("""
                    INSERT INTO global_contacts
                        (id, name, email, company, domain,
                         linkedin_url, role, verified, found_via)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (email) DO UPDATE
                    SET name         = EXCLUDED.name,
                        linkedin_url = EXCLUDED.linkedin_url,
                        role         = EXCLUDED.role,
                        verified     = EXCLUDED.verified
                """, (
                    str(uuid.uuid4()),
                    c.get("name",         "")[:255],
                    email[:255],
                    c.get("company",      "")[:255],
                    c.get("domain",       "")[:255],
                    c.get("linkedin_url", "")[:500],
                    c.get("role",         "")[:100],
                    c.get("verified",     False),
                    c.get("found_via",    "")[:100]
                ))
                if cur.rowcount > 0:
                    saved += 1

            except Exception as e:
                print(f"   ⚠️  Skip {email}: {e}")
                continue

        db.commit()
        print(f"   ✅ Saved {saved} new contacts")

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

def summary_node(state: ContactState) -> ContactState:
    """Print contact finding summary."""
    contacts = state["all_contacts"]

    print(f"\n{'='*55}")
    print(f"✅ Contact Finder — {state['company']}")
    print(f"{'='*55}")
    print(f"   HR Contacts  : {len(state['hr_contacts'])}")
    print(f"   Employees    : {len(state['employee_contacts'])}")
    print(f"   Total        : {len(contacts)}")
    print(f"   Saved to DB  : {state['saved_count']}")

    print(f"\n   Contacts found:")
    for c in contacts[:5]:
        has_email = "📧" if c.get("email") else "  "
        has_li    = "🔗" if c.get("linkedin_url") else "  "
        print(f"   {has_email}{has_li} {c.get('name','Unknown'):25s}"
              f" | {c.get('role',''):20s}"
              f" | {c.get('email','no email')}")

    print(f"{'='*55}\n")
    return state


# ══════════════════════════════════════════════════════════════════════════════
# DB CACHE HELPER
# ══════════════════════════════════════════════════════════════════════════════

def get_cached_contacts(company: str, contact_type: str) -> list:
    """Check if we already have contacts for this company in DB."""
    try:
        from db.connection import get_db_connection
        db  = get_db_connection()
        cur = db.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS global_contacts (
                id VARCHAR(255) PRIMARY KEY,
                name VARCHAR(255),
                email VARCHAR(255) UNIQUE,
                company VARCHAR(255),
                domain VARCHAR(255),
                linkedin_url VARCHAR(500),
                role VARCHAR(100),
                verified BOOLEAN DEFAULT FALSE,
                found_via VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        if contact_type == "hr":
            cur.execute("""
                SELECT id, name, email, company, domain,
                       linkedin_url, role, verified, found_via
                FROM global_contacts
                WHERE LOWER(company) = LOWER(%s)
                AND LOWER(role) LIKE ANY(ARRAY[
                    '%hr%','%recruit%','%talent%','%hiring%','%people%'
                ])
                LIMIT 3
            """, (company,))
        else:
            cur.execute("""
                SELECT id, name, email, company, domain,
                       linkedin_url, role, verified, found_via
                FROM global_contacts
                WHERE LOWER(company) = LOWER(%s)
                AND LOWER(role) NOT LIKE ANY(ARRAY[
                    '%hr%','%recruit%','%talent%'
                ])
                LIMIT 5
            """, (company,))

        rows    = cur.fetchall()
        columns = ["id","name","email","company","domain",
                   "linkedin_url","role","verified","found_via"]
        cur.close()
        db.close()
        return [dict(zip(columns, r)) for r in rows]

    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# BUILD LANGGRAPH PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def build_contact_graph():
    """Build LangGraph pipeline for contact finding."""
    graph = StateGraph(ContactState)

    graph.add_node("extract_domain"     , extract_domain_node)
    graph.add_node("find_hr"            , find_hr_emails_node)
    graph.add_node("find_employees"     , find_employees_node)
    graph.add_node("find_employee_emails", find_employee_emails_node)
    graph.add_node("enrich"             , enrich_contacts_node)
    graph.add_node("save"               , save_contacts_node)
    graph.add_node("summary"            , summary_node)

    graph.set_entry_point("extract_domain")
    graph.add_edge("extract_domain"     , "find_hr")
    graph.add_edge("find_hr"            , "find_employees")
    graph.add_edge("find_employees"     , "find_employee_emails")
    graph.add_edge("find_employee_emails", "enrich")
    graph.add_edge("enrich"             , "save")
    graph.add_edge("save"               , "summary")
    graph.add_edge("summary"            , END)

    return graph.compile()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION — CALL FOR SINGLE JOB
# ══════════════════════════════════════════════════════════════════════════════

def find_contacts_for_job(job: dict) -> dict:
    """
    Find all contacts and company details for a single job.
    Returns dict with company_phone and contacts list.
    """
    pipeline    = build_contact_graph()
    final_state = pipeline.invoke({
        "job"              : job,
        "company"          : job.get("company", ""),
        "domain"           : "",
        "company_phone"    : "",
        "hr_contacts"      : [],
        "employee_contacts": [],
        "all_contacts"     : [],
        "saved_count"      : 0,
        "error"            : None
    })
    return {
        "company_phone": final_state.get("company_phone", ""),
        "contacts": final_state["all_contacts"]
    }


# ══════════════════════════════════════════════════════════════════════════════
# BATCH FUNCTION — CALL FOR ALL TOP JOBS
# ══════════════════════════════════════════════════════════════════════════════

def find_contacts_for_all_jobs(top_jobs: list) -> dict:
    """
    Find contacts for all top matched jobs.
    Returns dict: {job_id: [contacts]}
    """
    print(f"\n🚀 Contact Finder — Processing {len(top_jobs)} jobs")
    results = {}

    for i, job in enumerate(top_jobs, 1):
        print(f"\n[{i}/{len(top_jobs)}] {job.get('company','Unknown')}")
        try:
            contacts           = find_contacts_for_job(job)
            results[job["id"]] = contacts
            time.sleep(3)  # polite delay between companies
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results[job["id"]] = []

    # Summary
    total = sum(len(v) for v in results.values())
    with_email = sum(
        1 for contacts in results.values()
        for c in contacts if c.get("email")
    )
    print(f"\n{'='*55}")
    print(f"✅ Contact Finder Complete")
    print(f"   Jobs processed : {len(top_jobs)}")
    print(f"   Total contacts : {total}")
    print(f"   With email     : {with_email}")
    print(f"{'='*55}")

    return results


