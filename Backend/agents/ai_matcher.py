import os
import json
import uuid
import asyncio
from typing import TypedDict, List, Optional
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END
from sentence_transformers import SentenceTransformer, util

load_dotenv()

# ─── LLM Setup ───────────────────────────────────────────────────────────────
llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model="openai/gpt-oss-120b",
    temperature=0
)

# ─── Sentence Transformer (offline, free, no API) ────────────────────────────
print("⏳ Loading sentence transformer model...")
embedder = SentenceTransformer("all-MiniLM-L6-v2")
print("✅ Model loaded")


# ══════════════════════════════════════════════════════════════════════════════
# LANGGRAPH STATE — data that flows between all nodes
# ══════════════════════════════════════════════════════════════════════════════

class MatcherState(TypedDict):
    user_id       : str
    resume        : dict           # parsed resume from Agent 1
    jobs          : List[dict]     # all jobs from Agent 4
    scored_jobs   : List[dict]     # jobs with match scores
    top_jobs      : List[dict]     # top 10 final jobs
    table_type    : str            # 'jobs', 'local_jobs', or 'mnc_jobs'
    error         : Optional[str]


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1 — LOAD JOBS FROM DB
# ══════════════════════════════════════════════════════════════════════════════

def load_jobs_node(state: MatcherState) -> MatcherState:
    """Load all unmatched jobs from PostgreSQL for this user."""
    from db.connection import get_db_connection

    print("\n📂 Loading jobs from database...")
    db  = get_db_connection()
    cur = db.cursor()

    try:
        table = state.get("table_type", "jobs")
        matches_table = "job_matches"
        job_id_col = "job_id"
        if table == "local_jobs":
            matches_table = "local_job_matches"
            job_id_col = "local_job_id"
        elif table == "mnc_jobs":
            matches_table = "mnc_job_matches"
            job_id_col = "mnc_job_id"
        elif table == "linkedin_jobs":
            matches_table = "linkedin_job_matches"
            job_id_col = "linkedin_job_id"
        
        # Ensure matches table exists
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {matches_table} (
                id VARCHAR(255) PRIMARY KEY,
                user_id VARCHAR(255),
                {job_id_col} VARCHAR(255),
                match_score NUMERIC,
                match_reason TEXT,
                is_notified BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, {job_id_col})
            )
        """)
        db.commit()
        
        # Pre-check/Create tables for LinkedIn if requested
        if table == "linkedin_jobs":
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
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {matches_table} (
                    id VARCHAR(255) PRIMARY KEY,
                    user_id VARCHAR(255),
                    {job_id_col} VARCHAR(255),
                    match_score INTEGER,
                    match_reason TEXT,
                    is_notified BOOLEAN DEFAULT FALSE,
                    UNIQUE(user_id, {job_id_col})
                )
            """)
            db.commit()

        # Get jobs not yet matched for this user
        cur.execute(f"""
            SELECT j.id, j.title, j.company, j.location,
                   j.source, j.url, j.description, j.job_type, j.scraped_at, j.raw_data
            FROM {table} j
            LEFT JOIN {matches_table} jm
                ON j.id::varchar = jm.{job_id_col}::varchar AND jm.user_id::varchar = %s
            WHERE jm.id IS NULL
            ORDER BY j.scraped_at DESC
            LIMIT 500
        """, (str(state["user_id"]),))

        rows    = cur.fetchall()
        columns = ["id", "title", "company", "location",
                   "source", "url", "description", "job_type", "scraped_at", "raw_data"]
        jobs    = [dict(zip(columns, row)) for row in rows]

        print(f"   ✅ Loaded {len(jobs)} unmatched jobs")
        return {**state, "jobs": jobs}

    except Exception as e:
        print(f"   ❌ Error loading jobs: {e}")
        return {**state, "error": str(e), "jobs": []}

    finally:
        cur.close()
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2 — FAST PRE-FILTER (sentence transformers, offline)
# ══════════════════════════════════════════════════════════════════════════════

def prefilter_node(state: MatcherState) -> MatcherState:
    """
    Fast semantic similarity scoring using sentence-transformers.
    Runs completely offline — no API needed.
    Filters jobs from 100 → top 30 before sending to LLM.
    """
    print("\n⚡ Pre-filtering with semantic similarity...")

    resume  = state["resume"]
    jobs    = state["jobs"]

    if not jobs:
        return {**state, "jobs": []}

    # Build resume text for embedding
    resume_text = " ".join([
        resume.get("summary", ""),
        " ".join(resume.get("skills", [])),
        " ".join(resume.get("job_titles", [])),
        f"{resume.get('experience_years', 0)} years experience",
        resume.get("education", "")
    ])

    # Embed resume once
    resume_embedding = embedder.encode(resume_text, convert_to_tensor=True)

    # Embed all job descriptions
    scored = []
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    for job in jobs:
        job_text = f"{job.get('title', '')} {job.get('company', '')} {job.get('description', '')[:500]}"
        job_embedding = embedder.encode(job_text, convert_to_tensor=True)
        similarity_score = float(util.cos_sim(resume_embedding, job_embedding)) * 100
        
        # Add a recency boost to ensure new jobs make it to the "top 150" pool
        recency_boost = 0
        scraped_at = job.get("scraped_at")
        if scraped_at:
            try:
                # Handle naive vs aware
                if scraped_at.tzinfo is None:
                    delta = datetime.now() - scraped_at
                else:
                    delta = now - scraped_at
                
                hours = delta.total_seconds() / 3600
                if hours <= 48: recency_boost = 15 # Boost recent jobs
            except: pass
            
        scored.append({
            **job,
            "semantic_score": round(similarity_score + recency_boost, 1)
        })

    # Sort by boosted semantic score, keep top 150
    scored.sort(key=lambda x: x["semantic_score"], reverse=True)
    top_candidates = scored[:150]

    print(f"   ✅ Pre-filter: {len(jobs)} → {len(top_candidates)} jobs (pool increased to ensure recency)")
    return {**state, "jobs": top_candidates}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3 — DEEP AI SCORING (LangChain + Groq LLM)
# ══════════════════════════════════════════════════════════════════════════════

def score_job_with_llm(resume: dict, job: dict) -> dict:
    """
    Score a single job against resume with strict prioritization:
    1. Experience Fit (40%)
    2. Skills & Keywords (40%)
    3. Freshness/Recency (20%)
    """
    from datetime import datetime, timezone
    import re

    # ─── DATA EXTRACTION ──────────────────────────────────────────────────────
    skills = [s.lower() for s in resume.get("skills", [])]
    keywords = [k.lower() for k in resume.get("search_keywords", [])]
    titles = [t.lower() for t in resume.get("job_titles", [])]
    user_exp = float(resume.get("experience_years", 0))

    job_title = job.get("title", "").lower()
    job_desc = job.get("description", "").lower()
    scraped_at = job.get("scraped_at")

    # ─── 1. EXPERIENCE SCORE (MAX 40) ─────────────────────────────────────────
    exp_score = 0
    exp_fit = "unknown"
    verdict = "Worth applying"
    
    # Try to find required years in description
    exp_match = re.search(r'(\d+)(?:\+|-(\d+))?\s*years?', job_desc)
    req_exp = None
    if exp_match:
        req_exp = float(exp_match.group(1))
    
    if req_exp is not None:
        diff = user_exp - req_exp
        if diff >= 0:
            if diff <= 2: # Perfect fit
                exp_score = 40
                exp_fit = "Perfect match"
            elif diff <= 5: # Good fit
                exp_score = 35
                exp_fit = "Good fit"
            else: # Overqualified
                exp_score = 25
                exp_fit = "Overqualified"
        else:
            # Underqualified
            if abs(diff) <= 1: # Slightly under
                exp_score = 15
                exp_fit = f"Slightly under ({req_exp}+ needed)"
                verdict = "Stretch role"
            else: # Far under
                exp_score = 0
                exp_fit = f"Requires {req_exp}+ years"
                verdict = "Not recommended"
    else:
        # No experience mentioned - assume entry/mid (neutral)
        exp_score = 30
        exp_fit = "Entry/Mid level"

    # ─── 2. SKILLS & KEYWORDS SCORE (MAX 40) ──────────────────────────────────
    matched_skills = [s for s in skills if s in job_desc or s in job_title]
    matched_keywords = [k for k in keywords if k in job_desc or k in job_title]
    
    # Calculate percentage of skills matched
    skill_match_ratio = len(matched_skills) / max(1, len(skills))
    keyword_match_ratio = len(matched_keywords) / max(1, len(keywords))
    
    # Skill points (max 30) + Title bonus (max 10)
    skill_points = (skill_match_ratio * 20) + (keyword_match_ratio * 10)
    title_bonus = 10 if any(t in job_title for t in titles) else 0
    
    skills_score = skill_points + title_bonus

    # ─── 3. RECENCY SCORE (MAX 20) ───────────────────────────────────────────
    recency_score = 0
    if scraped_at:
        try:
            # Convert to naive or aware comparison
            now = datetime.now(timezone.utc)
            if scraped_at.tzinfo is None:
                now = datetime.now() # naive
            
            delta = now - scraped_at
            hours = delta.total_seconds() / 3600
            
            if hours <= 24: # Today
                recency_score = 20
            elif hours <= 48: # Yesterday
                recency_score = 15
            elif hours <= 168: # Within week
                recency_score = 10
            else:
                recency_score = 5
        except:
            recency_score = 10
    else:
        recency_score = 10 # Default neutral

    # ─── FINAL CALCULATION ────────────────────────────────────────────────────
    total_score = exp_score + skills_score + recency_score
    total_score = min(99, max(1, total_score)) # Keep within 1-99 range

    reason = f"Experience: {exp_fit}. "
    reason += f"Skills matched: {len(matched_skills)}/{len(skills)}. "
    if recency_score >= 15: reason += "Freshly posted! "

    return {
        "match_score"         : int(total_score),
        "match_reason"        : reason,
        "matching_skills"     : matched_skills,
        "missing_skills"      : [s for s in skills if s not in matched_skills],
        "experience_fit"      : exp_fit,
        "location_fit"        : "Matched" if resume.get("city","").lower() in job.get("location","").lower() else "Remote/Other",
        "apply_recommendation": verdict
    }


def deep_score_node(state: MatcherState) -> MatcherState:
    """
    Deep score top 30 jobs using rule-based algorithm.
    Combines skill, keyword, and experience score + semantic score for final ranking.
    Passes through remaining jobs as generic skill matches without deep AI cost.
    """
    import time
    
    print(f"\n🤖 Deep scoring top 30 jobs using rule-based algorithm...")

    resume         = state["resume"]
    jobs           = state["jobs"]
    scored_jobs    = []

    for i, job in enumerate(jobs):
        # Get rule-based score
        result = score_job_with_llm(resume, job)

        final_score = float(result.get("match_score", 0))

        scored_job = {
            **job,
            "match_score"         : final_score,
            "llm_score"           : final_score,
            "semantic_score"      : job.get("semantic_score", 0),
            "match_reason"        : result.get("match_reason", ""),
            "matching_skills"     : result.get("matching_skills", []),
            "missing_skills"      : result.get("missing_skills", []),
            "experience_fit"      : result.get("experience_fit", ""),
            "apply_recommendation": result.get("apply_recommendation", "")
        }
        scored_jobs.append(scored_job)
        
    # Sort by final score
    scored_jobs.sort(key=lambda x: x["match_score"], reverse=True)
    print(f"   ✅ Scoring complete")

    return {**state, "scored_jobs": scored_jobs}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4 — PICK TOP 10 AND SAVE TO DB
# ══════════════════════════════════════════════════════════════════════════════

def save_matches_node(state: MatcherState) -> MatcherState:
    """Save all match scores to job_matches table and return top 10."""
    from db.connection import get_db_connection

    print(f"\n💾 Saving match scores to database...")

    scored_jobs = state["scored_jobs"]
    user_id     = state["user_id"]

    db  = get_db_connection()
    cur = db.cursor()
    saved = 0

    try:
        table = state.get("table_type", "jobs")
        matches_table = "job_matches"
        job_id_col = "job_id"
        
        if table == "local_jobs":
            matches_table = "local_job_matches"
            job_id_col = "local_job_id"
        elif table == "mnc_jobs":
            matches_table = "mnc_job_matches"
            job_id_col = "mnc_job_id"
        elif table == "linkedin_jobs":
            matches_table = "linkedin_job_matches"
            job_id_col = "linkedin_job_id"
            
        # Migration for linkedin_job_matches
        if table == "linkedin_jobs":
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {matches_table} (
                    id VARCHAR(255) PRIMARY KEY,
                    user_id UUID,
                    {job_id_col} VARCHAR(255),
                    match_score INTEGER,
                    match_reason TEXT,
                    is_notified BOOLEAN DEFAULT FALSE,
                    UNIQUE(user_id, {job_id_col})
                )
            """)
            db.commit()
            
        for job in scored_jobs:
            cur.execute(f"""
                INSERT INTO {matches_table}
                    (id, user_id, {job_id_col}, match_score, match_reason, is_notified)
                VALUES (%s, %s::uuid, %s, %s, %s, false)
                ON CONFLICT (user_id, {job_id_col}) DO UPDATE
                SET match_score  = EXCLUDED.match_score,
                    match_reason = EXCLUDED.match_reason
            """, (
                str(uuid.uuid4()),
                str(user_id),
                str(job["id"]),
                job["match_score"],
                job.get("match_reason", "")
            ))
            saved += 1

        db.commit()
        print(f"   ✅ Saved {saved} match scores")

    except Exception as e:
        db.rollback()
        print(f"   ❌ DB error: {e}")

    finally:
        cur.close()
        db.close()

    # Pick top 100
    top_jobs = scored_jobs[:100]
    return {**state, "top_jobs": top_jobs}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 5 — PRINT FINAL RESULTS
# ══════════════════════════════════════════════════════════════════════════════

def results_node(state: MatcherState) -> MatcherState:
    """Display top matched jobs nicely."""

    top_jobs = state["top_jobs"]

    print(f"\n{'='*60}")
    print(f"🏆 TOP {len(top_jobs)} MATCHED JOBS FOR {state['resume'].get('name','')}")
    print(f"{'='*60}")

    for i, job in enumerate(top_jobs, 1):
        score = job.get("match_score", 0)
        emoji = "🔥" if score >= 80 else "✅" if score >= 60 else "⚠️"

        print(f"\n{emoji} #{i} — {job.get('title')} @ {job.get('company')}")
        print(f"   Score      : {score}%")
        print(f"   Location   : {job.get('location')}")
        print(f"   Source     : {job.get('source')}")
        print(f"   Reason     : {job.get('match_reason','')}")
        print(f"   Skills ✅  : {', '.join(job.get('matching_skills', [])[:4])}")
        print(f"   Missing ❌ : {', '.join(job.get('missing_skills', [])[:3])}")
        print(f"   Verdict    : {job.get('apply_recommendation','')}")
        print(f"   Apply      : {job.get('url','')}")

    print(f"\n{'='*60}\n")
    return state


# ══════════════════════════════════════════════════════════════════════════════
# BUILD LANGGRAPH PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def build_matcher_graph():
    """Build the LangGraph state machine for AI matching."""

    graph = StateGraph(MatcherState)

    # Add all nodes
    graph.add_node("load_jobs"  , load_jobs_node)
    graph.add_node("prefilter"  , prefilter_node)
    graph.add_node("deep_score" , deep_score_node)
    graph.add_node("save_matches", save_matches_node)
    graph.add_node("results"    , results_node)

    # Connect nodes in order
    graph.set_entry_point("load_jobs")
    graph.add_edge("load_jobs"   , "prefilter")
    graph.add_edge("prefilter"   , "deep_score")
    graph.add_edge("deep_score"  , "save_matches")
    graph.add_edge("save_matches", "results")
    graph.add_edge("results"     , END)

    return graph.compile()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION — CALL THIS FROM OTHER AGENTS
# ══════════════════════════════════════════════════════════════════════════════

def match_jobs(user_id: str, parsed_resume: dict) -> list:
    """Run standard jobs"""
    print(f"\n{'='*60}")
    print(f"🚀 AI Matcher Agent Started (Pan-India)")
    print(f"{'='*60}")
    pipeline = build_matcher_graph()
    state = pipeline.invoke({
        "user_id": user_id, "resume": parsed_resume, "jobs": [], "scored_jobs": [], "top_jobs": [], "table_type": "jobs", "error": None
    })
    return state["top_jobs"]

def match_local_jobs(user_id: str, parsed_resume: dict) -> list:
    """Run local jobs"""
    print(f"\n{'='*60}")
    print(f"🚀 AI Matcher Agent Started (Local City)")
    print(f"{'='*60}")
    pipeline = build_matcher_graph()
    state = pipeline.invoke({
        "user_id": user_id, "resume": parsed_resume, "jobs": [], "scored_jobs": [], "top_jobs": [], "table_type": "local_jobs", "error": None
    })
    return state["top_jobs"]

def match_mnc_jobs(user_id: str, parsed_resume: dict) -> list:
    """Run mnc jobs"""
    print(f"\n{'='*60}")
    print(f"🚀 AI Matcher Agent Started (MNC)")
    print(f"{'='*60}")
    pipeline = build_matcher_graph()
    state = pipeline.invoke({
        "user_id": user_id, "resume": parsed_resume, "jobs": [], "scored_jobs": [], "top_jobs": [], "table_type": "mnc_jobs", "error": None
    })
    return state["top_jobs"]

def match_linkedin_jobs(user_id: str, parsed_resume: dict) -> list:
    """Run linkedin jobs"""
    print(f"\n{'='*60}")
    print(f"🚀 AI Matcher Agent Started (LinkedIn)")
    print(f"{'='*60}")
    pipeline = build_matcher_graph()
    state = pipeline.invoke({
        "user_id": user_id, "resume": parsed_resume, "jobs": [], "scored_jobs": [], "top_jobs": [], "table_type": "linkedin_jobs", "error": None
    })
    return state["top_jobs"]
