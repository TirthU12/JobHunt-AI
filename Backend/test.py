import os
import sys
import asyncio
from dotenv import load_dotenv

# Fix terminal encoding issues on Windows
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

# Load environment variables FIRST
load_dotenv()

# Now import the agents
from agents.Linkedin_agent import search_linkedin_jobs
from agents.ai_matcher import match_linkedin_jobs

async def run_test():
    print("=" * 60, flush=True)
    print("🚀 Starting LinkedIn Agent Test", flush=True)
    print("=" * 60, flush=True)

    # 1. Mock Profile (Feel free to edit these values to match your resume)
    profile = {
        'user_id': '00000000-0000-0000-0000-000000000000',
        'keywords': ['software engineer', 'developer'],
        'city': 'Ahmedabad',
        'skills': ['Python', 'React', 'Node.js', 'PostgreSQL'],
        'experience_level': '',
        'resume_text': 'Software Engineer with 4 years of experience building full-stack web applications using Python, React, and PostgreSQL.'
    }
    
    print("\n[1] Testing search_linkedin_jobs (Scraping & Enriching)...", flush=True)
    raw_jobs = await search_linkedin_jobs(profile)
    print(f"✅ Finished Scraping. Found {len(raw_jobs)} jobs.", flush=True)

    if not raw_jobs:
        print("⚠️ No jobs found. Playwright might have been blocked or no matches.", flush=True)
    else:
        print("   Sample Jobs Scraped:", flush=True)
        for j in raw_jobs[:3]:
            print(f"    - {j.get('title')} @ {j.get('company')}", flush=True)

    print("\n[2] Testing match_linkedin_jobs (AI Scoring & DB Save)...", flush=True)
    try:
        top_jobs = match_linkedin_jobs(profile['user_id'], profile)
        print(f"✅ Finished Matching. Scored top {len(top_jobs)} jobs.", flush=True)

        if top_jobs:
            print("   Top Scored Jobs:", flush=True)
            for j in top_jobs[:3]:
                print(f"    - [Score: {j.get('match_score')}] {j.get('title')} @ {j.get('company')}", flush=True)
    except Exception as e:
        print(f"❌ AI Matcher Failed: {e}", flush=True)

    print("\n🎉 Test Complete!", flush=True)

if __name__ == "__main__":
    asyncio.run(run_test())
