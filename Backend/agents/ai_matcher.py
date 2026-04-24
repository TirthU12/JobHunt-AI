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
        
        # Get jobs not yet matched for this user
        cur.execute(f"""
            SELECT j.id, j.title, j.company, j.location,
                   j.source, j.url, j.description, j.job_type
            FROM {table} j
            LEFT JOIN {matches_table} jm
                ON j.id = jm.{job_id_col} AND jm.user_id = %s
            WHERE jm.id IS NULL
            ORDER BY j.scraped_at DESC
            LIMIT 300
        """, (state["user_id"],))

        rows    = cur.fetchall()
        columns = ["id", "title", "company", "location",
                   "source", "url", "description", "job_type"]
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
    for job in jobs:
        job_text = f"""
        {job.get('title', '')}
        {job.get('company', '')}
        {job.get('description', '')[:500]}
        {job.get('job_type', '')}
        """
        job_embedding    = embedder.encode(job_text, convert_to_tensor=True)
        similarity_score = float(util.cos_sim(resume_embedding, job_embedding))

        scored.append({
            **job,
            "semantic_score": round(similarity_score * 100, 1)
        })

    # Sort by semantic score, keep top 100 for LLM deep analysis and skill relevancy
    scored.sort(key=lambda x: x["semantic_score"], reverse=True)
    top_candidates = scored[:100]

    print(f"   ✅ Pre-filter: {len(jobs)} → {len(top_candidates)} jobs")
    print(f"   Top score: {top_candidates[0]['semantic_score']}% — {top_candidates[0]['title']} @ {top_candidates[0]['company']}")

    return {**state, "jobs": top_candidates}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3 — DEEP AI SCORING (LangChain + Groq LLM)
# ══════════════════════════════════════════════════════════════════════════════

def score_job_with_llm(resume: dict, job: dict) -> dict:
    """Score a single job against resume using LangChain + Groq."""

    parser = JsonOutputParser()
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert recruiter and career coach.
        Score how well a candidate matches a job posting.
        CRITICAL RULE: Experience is highly weighted. If the job requires 5+ years and the candidate has only 1 year, dynamically slash their match_score. 
        Likewise, do not give high scores if the candidate is severely underqualified.
        Return ONLY valid JSON — no explanation, no markdown."""),

        ("human", """
        Score this candidate for this job. Return JSON only:
        {{
          "match_score"         : <number 0-100>,
          "match_reason"        : "<2 sentence explanation>",
          "matching_skills"     : ["skill1", "skill2"],
          "missing_skills"      : ["skill1", "skill2"],
          "experience_fit"      : "<too junior / good fit / overqualified>",
          "location_fit"        : "<yes / remote ok / relocation needed>",
          "apply_recommendation": "<definitely apply / worth trying / skip>"
        }}

        CANDIDATE:
        - Name            : {name}
        - Skills          : {skills}
        - Experience      : {experience} years
        - Job Titles      : {titles}
        - Location        : {location}
        - Education       : {education}

        JOB:
        - Title       : {job_title}
        - Company     : {company}
        - Location    : {job_location}
        - Type        : {job_type}
        - Description : {description}
        """)
    ])

    chain = prompt | llm | parser

    try:
        result = chain.invoke({
            "name"        : resume.get("name", ""),
            "skills"      : ", ".join(resume.get("skills", [])[:15]),
            "experience"  : resume.get("experience_years", 0),
            "titles"      : ", ".join(resume.get("job_titles", [])),
            "location"    : resume.get("location", ""),
            "education"   : resume.get("education", ""),
            "job_title"   : job.get("title", ""),
            "company"     : job.get("company", ""),
            "job_location": job.get("location", ""),
            "job_type"    : job.get("job_type", ""),
            "description" : job.get("description", "")[:1500]
        })
        return result

    except Exception as e:
        print(f"   ⚠️  LLM scoring failed for {job.get('title')}: {e}")
        # Fallback to semantic score only
        return {
            "match_score"         : job.get("semantic_score", 0),
            "match_reason"        : "Scored by semantic similarity",
            "matching_skills"     : [],
            "missing_skills"      : [],
            "experience_fit"      : "unknown",
            "location_fit"        : "unknown",
            "apply_recommendation": "worth trying"
        }


def deep_score_node(state: MatcherState) -> MatcherState:
    """
    Deep score top 30 jobs using LangChain + Groq.
    Combines LLM score + semantic score for final ranking.
    Passes through remaining jobs as generic skill matches without deep AI cost.
    """
    import time
    
    print(f"\n🤖 Deep scoring top 15 jobs with Groq LLaMA 3.3 to respect rate limits...")

    resume         = state["resume"]
    jobs           = state["jobs"]
    jobs_to_score  = jobs[:15]
    jobs_unscored  = jobs[15:]
    scored_jobs    = []

    for i, job in enumerate(jobs_to_score):
        print(f"   [{i+1}/{len(jobs_to_score)}] Scoring: {job.get('title')} @ {job.get('company')}")

        # Get LLM score
        llm_result = score_job_with_llm(resume, job)

        # Combine: 60% LLM score + 40% semantic score
        llm_score      = float(llm_result.get("match_score", 0))
        semantic_score = float(job.get("semantic_score", 0))
        final_score    = round((llm_score * 0.6) + (semantic_score * 0.4), 1)

        scored_job = {
            **job,
            "match_score"         : final_score,
            "llm_score"           : llm_score,
            "semantic_score"      : semantic_score,
            "match_reason"        : llm_result.get("match_reason", ""),
            "matching_skills"     : llm_result.get("matching_skills", []),
            "missing_skills"      : llm_result.get("missing_skills", []),
            "experience_fit"      : llm_result.get("experience_fit", ""),
            "apply_recommendation": llm_result.get("apply_recommendation", "")
        }
        scored_jobs.append(scored_job)
        time.sleep(2) # Prevent Groq Free Tier TPM burst limits!
        
    for job in jobs_unscored:
        scored_jobs.append({
            **job,
            "match_score"         : job.get("semantic_score", 0),
            "llm_score"           : 0,
            "semantic_score"      : float(job.get("semantic_score", 0)),
            "match_reason"        : "Job is highly relevant to your skills (AI Semantic Pre-filter), but skipped deep analysis to save time.",
            "matching_skills"     : [],
            "missing_skills"      : [],
            "experience_fit"      : "unknown",
            "location_fit"        : "unknown",
            "apply_recommendation": "evaluate manually"
        })

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
            
        for job in scored_jobs:
            cur.execute(f"""
                INSERT INTO {matches_table}
                    (id, user_id, {job_id_col}, match_score, match_reason, is_notified)
                VALUES (%s, %s, %s, %s, %s, false)
                ON CONFLICT (user_id, {job_id_col}) DO UPDATE
                SET match_score  = EXCLUDED.match_score,
                    match_reason = EXCLUDED.match_reason
            """, (
                str(uuid.uuid4()),
                user_id,
                job["id"],
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
