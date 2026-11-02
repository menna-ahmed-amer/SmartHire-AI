from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    MODEL_AVAILABLE = True
except Exception:
    MODEL_AVAILABLE = False
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "jobs.csv"

app = FastAPI(title="HireSense AI API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SKILL_KEYWORDS = [
    "python", "java", "javascript", "html", "css", "react", "fastapi", "django",
    "sql", "excel", "power bi", "tableau", "statistics", "data analysis", "dashboards",
    "machine learning", "deep learning", "nlp", "tensorflow", "pytorch", "pandas", "numpy",
    "recruitment", "screening", "interviews", "onboarding", "employee relations", "hr policies",
    "communication", "payroll", "hris", "documentation", "training", "performance management",
    "reporting", "administration", "git", "apis", "databases", "debugging", "leadership",
    "project management", "customer service", "marketing", "sales", "accounting", "finance"
]


def clean_text(text: str) -> str:
    text = text or ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_column_map(df: pd.DataFrame) -> dict[str, str]:
    return {str(c).strip().lower().replace("_", " "): c for c in df.columns}


def col(df: pd.DataFrame, *names: str) -> str | None:
    cmap = normalize_column_map(df)
    for name in names:
        key = name.strip().lower().replace("_", " ")
        if key in cmap:
            return cmap[key]
    return None


@lru_cache(maxsize=1)
def load_jobs() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise RuntimeError(f"jobs.csv not found at {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    df = df.fillna("")
    title = col(df, "Job Title", "title", "job_title")
    desc = col(df, "Job Description", "description", "job_description")
    skills = col(df, "Skills", "Required Skills", "skills")
    resp = col(df, "Responsibilities", "responsibilities")
    company = col(df, "Company", "Company Name", "company_name")
    if not title or not desc:
        raise RuntimeError("jobs.csv must contain at least Job Title and Job Description columns")
    df["_title"] = df[title].astype(str)
    df["_description"] = df[desc].astype(str)
    df["_skills"] = df[skills].astype(str) if skills else ""
    df["_responsibilities"] = df[resp].astype(str) if resp else ""
    df["_company"] = df[company].astype(str) if company else "Unknown Company"
    df["_search_text"] = (
        df["_title"] + ". " + df["_description"] + ". Skills: " + df["_skills"] + ". " + df["_responsibilities"]
    ).map(clean_text)
    return df


@lru_cache(maxsize=1)
def get_model():
    if not MODEL_AVAILABLE:
        return None
    return SentenceTransformer("all-MiniLM-L6-v2")


def semantic_scores(query: str, documents: list[str]) -> np.ndarray:
    query = clean_text(query)
    documents = [clean_text(d) for d in documents]
    if not documents:
        return np.array([])
    if MODEL_AVAILABLE:
        model = get_model()
        vectors = model.encode([query] + documents, convert_to_numpy=True, show_progress_bar=False)
        sims = cosine_similarity([vectors[0]], vectors[1:])[0]
        return sims
    vectorizer = TfidfVectorizer(stop_words="english", max_features=12000)
    vectors = vectorizer.fit_transform([query] + documents)
    return cosine_similarity(vectors[0], vectors[1:]).ravel()


async def extract_pdf_text(upload: UploadFile) -> str:
    data = await upload.read()
    if not data:
        return ""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return clean_text(text)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF {upload.filename}: {exc}") from exc


def parse_skills_from_text(text: str) -> set[str]:
    lowered = clean_text(text).lower()
    found = {skill.title() for skill in SKILL_KEYWORDS if skill in lowered}
    return found


def parse_skills_cell(text: str) -> set[str]:
    raw = clean_text(text)
    parts = re.split(r",|;|\||/|\n", raw)
    skills = {p.strip().title() for p in parts if len(p.strip()) > 1}
    return skills | parse_skills_from_text(raw)


def skill_gap(cv_text: str, required_skills_text: str) -> dict[str, Any]:
    required = parse_skills_cell(required_skills_text)
    cv_skills = parse_skills_from_text(cv_text)
    matched = sorted(required & cv_skills)
    missing = sorted(required - cv_skills)
    rate = round((len(matched) / len(required) * 100), 1) if required else 0.0
    return {"matched_skills": matched, "missing_skills": missing, "skill_match_rate": rate}


def status_from_score(score: float) -> tuple[str, str]:
    pct = score * 100
    if pct >= 85:
        return "Highly Recommended", "high"
    if pct >= 70:
        return "Good Match", "good"
    return "Weak Match", "weak"


@app.get("/health")
def health():
    return {"status": "ok", "model": "sentence-transformers" if MODEL_AVAILABLE else "tfidf-fallback"}


@app.post("/jobseeker/recommend")
async def recommend_jobs(
    cv: UploadFile = File(...),
    work_type: str = Form("Any"),
    experience: str = Form("Any"),
):
    cv_text = await extract_pdf_text(cv)
    if len(cv_text) < 30:
        raise HTTPException(status_code=400, detail="The uploaded CV text is too short or unreadable.")

    df = load_jobs().copy()
    work_col = col(df, "Work Type", "work_type")
    exp_col = col(df, "Experience", "experience")
    if work_col and work_type and work_type != "Any":
        df = df[df[work_col].astype(str).str.lower().str.contains(work_type.lower(), na=False)]
    if exp_col and experience and experience != "Any":
        df = df[df[exp_col].astype(str).str.lower().str.contains(experience.lower(), na=False)]
    if df.empty:
        df = load_jobs().copy()

    scores = semantic_scores(cv_text, df["_search_text"].tolist())
    df["_score"] = scores
    top = df.sort_values("_score", ascending=False).head(10)

    recommendations = []
    for rank, (_, row) in enumerate(top.iterrows(), start=1):
        gap = skill_gap(cv_text, str(row.get("_skills", "")))
        recommendations.append({
            "rank": rank,
            "job_title": row["_title"],
            "company": row["_company"],
            "match_score": round(float(row["_score"]) * 100, 1),
            "required_skills": str(row.get("_skills", "")),
            "matched_skills": gap["matched_skills"],
            "missing_skills": gap["missing_skills"],
            "skill_match_rate": gap["skill_match_rate"],
        })

    best = recommendations[0] if recommendations else None
    return {
        "best_title": best["job_title"] if best else "No match",
        "best_score": best["match_score"] if best else 0,
        "summary": f"Your CV is most aligned with {best['job_title']} roles. The ranking is based on semantic similarity, required skills, and responsibilities." if best else "No matching jobs found.",
        "recommendations": recommendations,
    }


@app.post("/employer/rank")
async def rank_candidates(
    job_title: str = Form(""),
    job_description: str = Form(...),
    cvs: list[UploadFile] = File(...),
):
    job_text = clean_text(job_title + ". " + job_description)
    if len(job_text) < 20:
        raise HTTPException(status_code=400, detail="Please enter a longer job description.")
    if not cvs:
        raise HTTPException(status_code=400, detail="Please upload at least one candidate CV.")

    cv_payloads = []
    for upload in cvs:
        text = await extract_pdf_text(upload)
        cv_payloads.append({"name": upload.filename, "text": text})

    scores = semantic_scores(job_text, [c["text"] for c in cv_payloads])
    required_skills = ", ".join(sorted(parse_skills_from_text(job_text)))

    candidates = []
    for i, (payload, score) in enumerate(zip(cv_payloads, scores), start=1):
        gap = skill_gap(payload["text"], required_skills)
        status, cls = status_from_score(float(score))
        candidates.append({
            "candidate_name": payload["name"],
            "match_score": round(float(score) * 100, 1),
            "matched_skills": gap["matched_skills"],
            "missing_skills": gap["missing_skills"],
            "skill_match_rate": gap["skill_match_rate"],
            "status": status,
            "class_name": cls,
        })
    candidates.sort(key=lambda x: x["match_score"], reverse=True)
    for rank, c in enumerate(candidates, start=1):
        c["rank"] = rank

    best = candidates[0] if candidates else None
    return {
        "top_score": best["match_score"] if best else 0,
        "status": "Strong shortlist" if best and best["match_score"] >= 80 else "Shortlist ready",
        "summary": "The top candidate has the strongest semantic alignment with the job description and required skills." if best else "No candidates found.",
        "candidates": candidates,
    }
