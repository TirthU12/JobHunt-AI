import os
import json
import uuid
import PyPDF2
import docx
import spacy
import re
 
from groq import Groq
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List, Optional
 
load_dotenv()
 
# ─── Load spaCy model ────────────────────────────────────────────────────────
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("⚠️  spaCy model not found. Run: python -m spacy download en_core_web_sm")
    nlp = None

from db.connection import get_db_connection
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


llm = ChatGroq(
    api_key=os.getenv("GROQ_API_KEY"),
    model="openai/gpt-oss-120b",
    temperature=0
)


class ResumeData(BaseModel):
    name: str = Field(description="Full name of the candidate")
    email: str = Field(description="Email address")
    phone: str = Field(description="Phone number")
    location: str = Field(description="City and country of the candidate")
    summary: str = Field(description="Professional summary or objective")
    skills: List[str] = Field(description="List of technical and soft skills")
    job_titles: List[str] = Field(description="Previous and desired job titles")
    search_keywords: List[str] = Field(description="Highly targeted keywords for querying job posting boards (e.g., 'React Developer', 'DevOps AWS')")
    experience_years: int = Field(description="Total years of experience")
    education: str = Field(description="Highest education qualification")
    languages: List[str] = Field(description="Spoken/written languages")
    certifications: List[str] = Field(description="Professional certifications if any")
    linkedin_url: Optional[str] = Field(description="LinkedIn profile URL if present")
    github_url: Optional[str] = Field(description="GitHub profile URL if present")
    salary_expectation: Optional[str] = Field(description="Expected salary if mentioned")




# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — EXTRACT RAW TEXT FROM FILE
# ══════════════════════════════════════════════════════════════════════════════


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF file."""
    text = ""
    try:
        with open(file_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
    return text


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX file."""
    text = ""
    try:
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
    except Exception as e:
        print(f"Error extracting text from DOCX: {e}")
    return text


def extract_text_from_resume(file_path: str) -> str:
    """Extract text from resume file (PDF or DOCX)."""
    if file_path.endswith(".pdf"):
        return extract_text_from_pdf(file_path)
    elif file_path.endswith(".docx"):
        return extract_text_from_docx(file_path)
    else:
        raise ValueError("Unsupported file format. Use PDF or DOCX.")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — PRE-PROCESS WITH spaCy (fast, free, offline)
# ══════════════════════════════════════════════════════════════════════════════


def preprocess_with_spacy(text: str)->dict:
    """Use spaCy to quickly extract basic entities before sending to LLM."""
    result={
        "email_found":[],
        "phone_found":[],
        "linkedin_found":[],
        "github_found":[],
        "skills_found":[],
        "experience_found":[],
        "education_found":[],       
        "languages_found":[],
        "certifications_found":[],
        "location_found":[],
        "name_found":[],
        "summary_found":[],
        "job_titles_found":[],
        "salary_expectation_found":[],
    }

    if not nlp:
        return result


    emails=re.findall(r'[\w\.-]+@[\w\.-]+',text)
    result["email_found"]=emails

    phones=re.findall(r'\+?\d{1,4}[\s\-]?\d{3,4}[\s\-]?\d{4,6}',text)
    result["phone_found"]=phones

    linkedin=re.findall(r'linkedin.com/in/[a-zA-Z0-9_-]+',text)
    result["linkedin_found"]=linkedin

    github=re.findall(r'github.com/[a-zA-Z0-9_-]+',text)
    result["github_found"]=github

    skills=re.findall(r'\b(?:Python|Java|C\+\+|JavaScript|React|Angular|Node.js|SQL|Git|Docker|AWS|Azure|GCP|Machine Learning|Deep Learning|Data Science|AI|NLP|Tableau|PowerBI|Excel|Communication|Teamwork|Problem Solving|Leadership|Time Management)\b',text,re.IGNORECASE)
    result["skills_found"]=skills

    experience=re.findall(r'\b(?:Software Engineer|Data Scientist|Project Manager|Product Manager|Business Analyst|Consultant|Developer|Intern|Trainee|Analyst|Manager|Director|Lead|Senior|Junior|Full Stack|Frontend|Backend|Mobile)\b',text,re.IGNORECASE)
    result["experience_found"]=experience

    education=re.findall(r'\b(?:Bachelor|Master|PhD|Diploma|Certificate|B.Tech|M.Tech|BCA|MCA|MBA|BBA|B.Sc|M.Sc|B.Com|M.Com|B.A|M.A|B.S|M.S)\b',text,re.IGNORECASE)
    result["education_found"]=education


    return result


 
# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — PARSE WITH LangChain + Groq LLM
# ══════════════════════════════════════════════════════════════════════════════

def parse_with_langchain(raw_text:str , spacy_result:dict)->dict:
    """Use LangChain + Groq LLM to parse resume and return structured JSON."""
    parser=JsonOutputParser(pydantic_object=ResumeData)

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert resume parser.
        Extract information from the resume text and return ONLY valid JSON.
        Do not include any explanation or markdown — just the JSON object.
        If a field is not found, use empty string "" or empty list [].
        For experience_years, estimate based on work history dates."""),
 
        ("human", """Parse this resume and return JSON matching this schema:
        {format_instructions}
 
        Hints from pre-processing:
        - Emails found: {emails}
        - URLs found: {urls}
 
        Resume Text:
        {resume_text}
        """)
    ])
 
    chain = prompt | llm | parser

    try:
        result=chain.invoke({
            "format_instructions": parser.get_format_instructions(),
            "emails": spacy_result["email_found"],
            "urls": spacy_result["linkedin_found"] + spacy_result["github_found"],
            "resume_text": raw_text[:4000]
        })
        return result
    except Exception as e:
        print(f"Error parsing with LangChain: {e}")
        return None


def parse_with_groq_direct(raw_text: str) -> dict:
    """Direct Groq API call as fallback — no LangChain."""
    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        temperature=0,
        messages=[{
            "role": "user",
            "content": f"""Parse this resume. Return ONLY a JSON object with these exact keys:
            name, email, phone, location, summary, skills (array), job_titles (array), search_keywords (array),
            experience_years (number), education, languages (array),
            certifications (array), linkedin_url, github_url, salary_expectation
 
            Resume:
            {raw_text[:4000]}
 
            Return ONLY JSON. No explanation. No markdown.
            """
        }]
    )
 
    raw = response.choices[0].message.content
    # Clean up markdown fences if present
    raw = raw.replace("```json", "").replace("```", "").strip()
 
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Find JSON object in response manually
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError("Could not parse JSON from LLM response")




# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — VALIDATE AND CLEAN PARSED DATA
# ══════════════════════════════════════════════════════════════════════════════

def validate_and_clean(parsed: dict, spacy_hints: dict) -> dict:
    """Clean up and validate the parsed resume data."""
 
    # Fill missing email from spaCy if LLM missed it
    if not parsed.get("email") and spacy_hints.get("emails_found"):
        parsed["email"] = spacy_hints["emails_found"][0]
 
    # Fill missing LinkedIn/GitHub from URLs found
    for url in spacy_hints.get("urls_found", []):
        if "linkedin.com" in url and not parsed.get("linkedin_url"):
            parsed["linkedin_url"] = url
        if "github.com" in url and not parsed.get("github_url"):
            parsed["github_url"] = url
 
    # Ensure skills is always a list
    if isinstance(parsed.get("skills"), str):
        parsed["skills"] = [s.strip() for s in parsed["skills"].split(",")]
 
    # Ensure job_titles is always a list
    if isinstance(parsed.get("job_titles"), str):
        parsed["job_titles"] = [parsed["job_titles"]]
 
    # Ensure experience_years is an int
    try:
        parsed["experience_years"] = int(parsed.get("experience_years", 0))
    except (ValueError, TypeError):
        parsed["experience_years"] = 0
 
    # Remove empty strings from lists
    for key in ["skills", "job_titles", "search_keywords", "languages", "certifications"]:
        if isinstance(parsed.get(key), list):
            parsed[key] = [item for item in parsed[key] if item and str(item).strip()]
 
    # Capitalize name
    if parsed.get("name"):
        parsed["name"] = parsed["name"].title()
 
    return parsed


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — SAVE TO DATABASE
# ══════════════════════════════════════════════════════════════════════════════


def save_user_and_resume(file_name: str, raw_text: str, parsed_data: dict):
    """Save user details and their resume in a single transaction."""
    from db.connection import get_db_connection
    conn = get_db_connection()
    if not conn:
        return None
    
    email = parsed_data.get("email")
    if not email:
        print("Error: No email found in parsed resume. Cannot create or link user.")
        return None
        
    name = parsed_data.get("name")
    location = parsed_data.get("location")
    
    try:
        cursor = conn.cursor()
        
        # 1. Insert or update user based on email (which is UNIQUE)
        cursor.execute("""
        INSERT INTO users (email, name, location)
        VALUES (%s, %s, %s)
        ON CONFLICT (email) DO UPDATE 
        SET name = COALESCE(EXCLUDED.name, users.name),
            location = COALESCE(EXCLUDED.location, users.location)
        RETURNING id;
        """, (email, name, location))
        
        user_id = cursor.fetchone()[0]
        
        # 2. Insert the resume with the retrieved user_id
        cursor.execute("""
        INSERT INTO resumes (user_id, file_name, raw_text, parsed_data)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
        """, (user_id, file_name, raw_text, json.dumps(parsed_data)))
        
        resume_id = cursor.fetchone()[0]
        
        conn.commit()
        return {"user_id": user_id, "resume_id": resume_id}
    except Exception as e:
        print(f"Error saving user and resume to database: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()


def process_resume(file_path: str) -> dict:
    """
    Full pipeline:
    1. Extract text from PDF/DOCX
    2. Pre-process with spaCy
    3. Parse with LangChain + Groq
    4. Validate and clean
    5. Save to DB
 
    Returns parsed resume data as dict.
    """
 
    file_name = os.path.basename(file_path)
    print(f"\n{'='*50}")
    print(f"🚀 Processing resume: {file_name}")
    print(f"{'='*50}")
 
    # Step 1: Extract text
    raw_text = extract_text_from_resume(file_path)
    if not raw_text or len(raw_text) < 50:
        raise ValueError("Could not extract meaningful text from resume file.")
    print(f"✅ Extracted {len(raw_text)} characters of text")
 
    # Step 2: spaCy pre-processing
    print("🔍 Running spaCy pre-processing...")
    spacy_hints = preprocess_with_spacy(raw_text)
    print(f"   Found emails: {spacy_hints.get('email_found', [])}")
    print(f"   Found URLs: {spacy_hints.get('linkedin_found', []) + spacy_hints.get('github_found', [])}")
 
    # Step 3: LLM parsing
    print("🤖 Parsing with LangChain + Groq (LLaMA 3.3)...")
    parsed = parse_with_langchain(raw_text, spacy_hints)
 
    # Step 4: Validate
    print("🧹 Validating and cleaning data...")
    parsed = validate_and_clean(parsed, spacy_hints)
 
    # Step 5: Save to DB
    print("💾 Saving to PostgreSQL...")
    db_result = save_user_and_resume(file_name, raw_text, parsed)
    if db_result:
        parsed["resume_id"] = db_result["resume_id"]
        parsed["user_id"] = db_result["user_id"]
    else:
        print("⚠️ Failed to save resume to DB")
 
    # Print summary
    print(f"\n{'='*50}")
    print(f"✅ Resume parsed successfully!")
    print(f"   Name     : {parsed.get('name')}")
    print(f"   Email    : {parsed.get('email')}")
    print(f"   Location : {parsed.get('location')}")
    print(f"   Skills   : {', '.join(parsed.get('skills', [])[:5])}...")
    print(f"   Exp      : {parsed.get('experience_years')} years")
    print(f"   Titles   : {parsed.get('job_titles')}")
    print(f"{'='*50}\n")
 
    return parsed
