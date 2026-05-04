import asyncio
import sys
import io

# Fix Windows encoding for emoji output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from agents.career_scraper import scrape_all_custom

async def main():
    print("Testing scrape_all_custom with keyword: 'software engineer'")
    print("=" * 60)
    jobs = await scrape_all_custom("software engineer")
    print(f"\n{'=' * 60}")
    print(f"TOTAL JOBS FOUND: {len(jobs)}")
    print(f"{'=' * 60}")
    for j in jobs[:15]:
        print(f"  [{j.get('source','?'):20s}] {j['title'][:60]}")
        print(f"    @ {j['company']} | {j['url'][:70]}")

asyncio.run(main())
