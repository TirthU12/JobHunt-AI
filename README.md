<p align="center">
  <img src="https://img.shields.io/badge/AI-Powered-blueviolet?style=for-the-badge&logo=openai&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" />
  <img src="https://img.shields.io/badge/LangGraph-FF6F00?style=for-the-badge&logo=langchain&logoColor=white" />
  <img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" />
</p>

<h1 align="center">🚀 JobHunt AI</h1>

<p align="center">
  <strong>An AI-powered job hunting platform that automatically parses your resume, scrapes 15+ job sources, and uses LLM-driven scoring to find your best-matched opportunities — all in one click.</strong>
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-agent-pipeline">Agent Pipeline</a> •
  <a href="#-tech-stack">Tech Stack</a> •
  <a href="#-getting-started">Getting Started</a> •
  <a href="#-api-reference">API Reference</a> •
  <a href="#-project-structure">Project Structure</a>
</p>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 📄 **Smart Resume Parsing** | Upload PDF/DOCX → spaCy NER pre-processing → LLM extraction via Groq for structured profile data (skills, experience, certifications, etc.) |
| 🌍 **Multi-Source Job Scraping** | Scrapes LinkedIn, Indeed, Glassdoor, Naukri, Internshala, RemoteOK, Jobicy, and more — all at once |
| 🏙️ **Hyper-Local City Search** | Discovers companies in your city via DuckDuckGo + LLM, then scrapes their career pages with Playwright |
| 🏢 **MNC Career Page Scraper** | Directly hits Lever & Greenhouse APIs for top Indian startups (Swiggy, Razorpay, CRED, PhonePe, Meesho, Zepto, etc.) |
| 🤖 **AI Job Matching (LangGraph)** | Two-stage scoring: fast semantic pre-filter (sentence-transformers) → deep LLM evaluation with Groq — experience, skill, and location fit analysis |
| 🎯 **User-Controlled Profile** | Edit AI-extracted resume data (skills, keywords, city) before triggering the heavy scraping pipeline |
| 💾 **PostgreSQL Persistence** | All jobs, matches, and user data stored with deduplication and conflict resolution |
| ⚡ **Experience-Aware Search** | Automatically appends "Entry Level" / "Junior" to queries based on candidate experience |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + Vite)                  │
│   Home → Upload Resume → Edit Profile → View Matched Jobs      │
└──────────────────────────────┬──────────────────────────────────┘
                               │ REST API
┌──────────────────────────────▼──────────────────────────────────┐
│                     FASTAPI BACKEND                             │
│                                                                 │
│  POST /parse-resume ──► Resume Parser Agent                     │
│  POST /search-jobs  ──► Orchestrator (triggers all agents)      │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    AGENT PIPELINE                          │  │
│  │                                                            │  │
│  │  ┌─────────────┐   ┌─────────────┐   ┌────────────────┐  │  │
│  │  │ Job Scraper  │   │ Local City  │   │ MNC Career     │  │  │
│  │  │ (Global)     │   │ Scraper     │   │ Scraper        │  │  │
│  │  │              │   │ (LangGraph) │   │ (Lever + GH)   │  │  │
│  │  └──────┬───────┘   └──────┬──────┘   └───────┬────────┘  │  │
│  │         │                  │                   │           │  │
│  │         ▼                  ▼                   ▼           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │            AI MATCHER (LangGraph Pipeline)           │  │  │
│  │  │                                                      │  │  │
│  │  │  Load Jobs → Semantic Pre-Filter → LLM Deep Score   │  │  │
│  │  │     → Save Matches → Return Top Results              │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                               │                                  │
│                    ┌──────────▼──────────┐                       │
│                    │    PostgreSQL DB     │                       │
│                    │  users | resumes    │                       │
│                    │  jobs | local_jobs  │                       │
│                    │  mnc_jobs | matches │                       │
│                    └─────────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🤖 Agent Pipeline

### Agent 1 — Resume Parser (`agents/resume_parser.py`)
> Extracts structured profile data from uploaded resumes.

| Step | Method | Details |
|------|--------|---------|
| 1 | **Text Extraction** | PyPDF2 / python-docx |
| 2 | **spaCy Pre-processing** | Regex + NER for emails, phones, URLs, skills |
| 3 | **LLM Parsing** | LangChain + Groq → structured JSON output |
| 4 | **Validation** | Data cleaning, type coercion, deduplication |
| 5 | **DB Save** | Upsert user + insert resume into PostgreSQL |

### Agent 2 — Job Scraper (`agents/job_scraper.py`)
> Multi-query scraping across global and India-specific job boards.

- **Global**: LinkedIn, Indeed, Glassdoor, ZipRecruiter via [JobSpy](https://github.com/Bunsly/JobSpy)
- **India**: Naukri, Internshala, Shine, TimesJobs, Foundit via Serper/SearchApi/DuckDuckGo
- **Remote**: RemoteOK, Jobicy (free public APIs — no key needed)
- **Smart Query Building**: Uses `search_keywords` + `job_titles` from parsed resume with experience-level injection

### Agent 3 — Local City Job Scraper (`agents/local_city_job_scraper.py`)
> LangGraph-powered pipeline for hyper-local job discovery.

```
discover_companies → scrape_boards → scrape_career_pages → merge_deduplicate → save_jobs → summary
```

- Discovers local companies via DuckDuckGo + LLM-generated company lists
- Scrapes career pages directly with **Playwright** (headless Chromium)
- Falls back to AI-powered HTML extraction when no structured job listings found

### Agent 4 — MNC Career Scraper (`agents/career_scraper.py`)
> Direct API access to career pages of top Indian tech companies.

| Platform | Companies |
|----------|-----------|
| **Lever** | Lenskart, Nykaa, Dunzo, Slice, Jupiter, FamPay, Cashfree |
| **Greenhouse** | Swiggy, Razorpay, Meesho, CRED, Groww, Zepto, PhonePe, Browserstack, Postman, Freshworks, Chargebee, Hasura, Setu |

### Agent 5 — AI Matcher (`agents/ai_matcher.py`)
> LangGraph state machine for intelligent job-candidate matching.

```
load_jobs → prefilter (semantic) → deep_score (LLM) → save_matches → results
```

| Stage | Method | Scale |
|-------|--------|-------|
| **Pre-filter** | Sentence-Transformers (`all-MiniLM-L6-v2`) — cosine similarity | 300 → 100 jobs |
| **Deep Score** | Groq LLM — skill match, experience fit, location fit analysis | Top 15 jobs |
| **Final Score** | 60% LLM score + 40% semantic score | Ranked list |

---

## 🛠 Tech Stack

### Backend
| Category | Technologies |
|----------|-------------|
| **Framework** | FastAPI, Uvicorn |
| **AI / LLM** | Groq (LLM inference), LangChain, LangGraph |
| **NLP** | spaCy, Sentence-Transformers, NLTK |
| **Scraping** | JobSpy, Playwright, BeautifulSoup, httpx, DuckDuckGo Search |
| **Database** | PostgreSQL, psycopg2, SQLAlchemy |
| **Task Queue** | Celery, Redis, Flower |
| **Auth** | python-jose (JWT), Passlib (bcrypt) |

### Frontend
| Category | Technologies |
|----------|-------------|
| **Framework** | React 19, TypeScript |
| **Build Tool** | Vite |
| **Styling** | TailwindCSS |
| **Animation** | Framer Motion |
| **Routing** | React Router DOM v7 |
| **Icons** | Lucide React |

---

## 🚀 Getting Started

### Prerequisites

- **Python** 3.12+
- **Node.js** 18+ & npm (or Bun)
- **PostgreSQL** running locally or cloud (e.g., Supabase, Neon)
- **Groq API Key** — [Get one free](https://console.groq.com/)
- (Optional) **Serper API Key** — for enhanced India job board scraping

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/jobhunt-ai.git
cd jobhunt-ai
```

### 2. Backend Setup

```bash
cd Backend

# Create virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_sm

# Install Playwright browsers (for local city scraping)
playwright install chromium
```

### 3. Environment Variables

Create a `.env` file in the `Backend/` directory:

```env
# ─── LLM ───────────────────────────────────
GROQ_API_KEY=your_groq_api_key_here

# ─── DATABASE ──────────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_NAME=jobhunt
DB_USER=postgres
DB_PASSWORD=your_password

# ─── OPTIONAL: Enhanced Scraping ───────────
SERPER_API_KEY=your_serper_key        # optional
SEARCH_API_KEY=your_searchapi_key     # optional
```

### 4. Database Setup

Create the PostgreSQL database:

```sql
CREATE DATABASE jobhunt;
```

> The application auto-creates tables on first run (e.g., `mnc_jobs`). For other tables, ensure your schema includes `users`, `resumes`, `jobs`, `local_jobs`, `job_matches`, `local_job_matches`, and `mnc_job_matches`.

### 5. Run the Backend

```bash
cd Backend
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`. Visit `http://localhost:8000/docs` for the interactive Swagger UI.

### 6. Frontend Setup

```bash
cd Frontend

# Install dependencies
npm install
# or
bun install

# Start dev server
npm run dev
```

The frontend will be available at `http://localhost:5173`.

---

## 📡 API Reference

### `GET /`
Health check — returns welcome message.

### `GET /health`
Checks database connectivity.

### `POST /parse-resume`
Upload and parse a resume file.

| Parameter | Type | Description |
|-----------|------|-------------|
| `resume` | `File` | PDF or DOCX resume file |

**Response:**
```json
{
  "message": "Resume parsed successfully. Please edit if needed.",
  "data": {
    "user_id": 1,
    "resume_id": 5,
    "name": "John Doe",
    "email": "john@example.com",
    "skills": ["Python", "React", "Docker"],
    "job_titles": ["Full Stack Developer"],
    "search_keywords": ["React Developer", "Python Backend"],
    "experience_years": 2,
    "location": "Bangalore, India"
  }
}
```

### `POST /search-jobs`
Trigger the full scraping + AI matching pipeline with edited profile data.

| Parameter | Type | Description |
|-----------|------|-------------|
| `payload` | `JSON Body` | Edited resume data including `user_id` |

**Response:**
```json
{
  "message": "Jobs scraped and AI dynamically matched successfully",
  "data": { ... },
  "jobs_scraped_amount": 150,
  "top_matched_jobs": [ ... ],
  "top_local_jobs": [ ... ]
}
```

---

## 📁 Project Structure

```
jobhunt-ai/
├── Backend/
│   ├── agents/
│   │   ├── resume_parser.py         # Agent 1: Resume parsing pipeline
│   │   ├── job_scraper.py           # Agent 2: Global + India job scraping
│   │   ├── local_city_job_scraper.py # Agent 3: LangGraph local city scraper
│   │   ├── career_scraper.py        # Agent 4: MNC Lever/Greenhouse scraper
│   │   ├── ai_matcher.py            # Agent 5: LangGraph AI matching pipeline
│   │   ├── company_finder.py        # Company discovery utilities
│   │   ├── contact_finder.py        # Contact information finder
│   │   ├── notifier.py              # Email notification agent
│   │   └── tracker.py               # Application tracking agent
│   ├── api/
│   │   └── routes.py                # API route definitions
│   ├── db/
│   │   ├── connection.py            # PostgreSQL connection manager
│   │   └── models.py                # Database models
│   ├── templates/                   # Email templates (Jinja2)
│   ├── main.py                      # FastAPI app entry point
│   ├── graph.py                     # LangGraph orchestration
│   ├── celery_worker.py             # Celery task worker
│   ├── requirements.txt             # Python dependencies
│   └── pyproject.toml               # Project metadata
│
├── Frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/              # Layout components (navbar, footer)
│   │   │   └── ui/                  # Reusable UI components
│   │   ├── pages/
│   │   │   ├── Home.tsx             # Landing page with resume upload
│   │   │   ├── Dashboard.tsx        # Job matches dashboard
│   │   │   ├── Products.tsx         # Job listings view
│   │   │   ├── Detail.tsx           # Individual job detail page
│   │   │   └── Login.tsx            # Authentication page
│   │   ├── lib/                     # Utility functions
│   │   ├── App.tsx                  # Root component with routing
│   │   └── main.tsx                 # React entry point
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
│
└── README.md
```

---

## 🔮 Roadmap

- [ ] **Real-time Job Alerts** — Celery beat scheduler for periodic scraping + email notifications
- [ ] **Application Tracker** — Track applied jobs, interviews, and offer stages
- [ ] **Chrome Extension** — One-click save jobs from any website
- [ ] **Resume Builder** — AI-powered resume generation tailored to specific job postings
- [ ] **Interview Prep** — Generate interview questions based on matched job descriptions
- [ ] **Multi-language Support** — Hindi and regional language resume parsing

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

<p align="center">
  Built with ❤️ and a lot of ☕
</p>
