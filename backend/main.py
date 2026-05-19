from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import json
import os
from dotenv import load_dotenv

from job_scraper import JobScraper

load_dotenv()

app = FastAPI(title="Job Scraping API", version="1.0.0")

# Configure CORS origins based on environment
DEVELOPMENT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000", 
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:4014",
    "http://127.0.0.1:4014",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
]

PRODUCTION_ORIGINS = [
    "https://mininglifeonline.com",
    "https://www.mininglifeonline.com",
    "https://api.mininglifeonline.com",
    "https://mininglifeserver.com",
    "https://mininglifeserver.com:8888",
]

# Get environment from environment variable, default to None for maximum flexibility
ENVIRONMENT = os.getenv("ENVIRONMENT")

if ENVIRONMENT == "production":
    allowed_origins = PRODUCTION_ORIGINS
    print(f"🚀 CORS: Production mode - allowed origins: {allowed_origins}")
elif ENVIRONMENT == "development":
    allowed_origins = DEVELOPMENT_ORIGINS + PRODUCTION_ORIGINS
    print(f"🛠️ CORS: Development mode - allowed origins: {allowed_origins}")
else:
    # When ENVIRONMENT is not set or set to anything else, allow all origins
    allowed_origins = ["https://api.mininglifeonline.com", "https://mininglifeonline.com", "https://www.mininglifeonline.com", "*"]
    print(f"🌐 CORS: Open mode (ENVIRONMENT={ENVIRONMENT}) - allowing ALL origins: {allowed_origins}")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False if allowed_origins == ["*"] else True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

class ScrapeRequest(BaseModel):
    url: str
    max_jobs: Optional[int] = 3  # Maximum number of jobs to scrape (default 3)

class JobData(BaseModel):
    employer: Optional[str] = None
    job_title: Optional[str] = None
    job_id: Optional[str] = None
    job_description: Optional[str] = None
    location: Optional[str] = None
    salary_range: Optional[str] = None
    application_deadline: Optional[str] = None
    image_url: Optional[str] = None
    key_responsibilities: Optional[str] = None
    qualifications_and_skills: Optional[str] = None
    required_experience: Optional[str] = None
    perks_and_benefits: Optional[str] = None
    preferred_years_of_experience: Optional[str] = None
    educational_level: Optional[str] = None
    certification_level: Optional[str] = None
    interview_format: Optional[str] = None
    html_content: Optional[str] = None
    source_url: Optional[str] = None

class ScrapeResponse(BaseModel):
    success: bool
    message: str
    jobs: List[JobData] = []
    total_jobs: int = 0

@app.get("/")
async def root():
    return {"message": "Job Scraping API is running"}

@app.get("/cors-test")
async def cors_test():
    return {
        "message": "CORS test successful",
        "environment": ENVIRONMENT,
        "allowed_origins": allowed_origins,
        "cors_enabled": True
    }

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_jobs(request: ScrapeRequest):
    try:
        # Initialize the job scraper
        scraper = JobScraper()
        
        # Scrape jobs from the provided URL (limited by max_jobs)
        jobs = await scraper.scrape_jobs(request.url, max_jobs=request.max_jobs)
        
        if not jobs:
            return ScrapeResponse(
                success=False,
                message="No jobs found or failed to scrape the website",
                jobs=[],
                total_jobs=0
            )
        
        return ScrapeResponse(
            success=True,
            message=f"Successfully scraped {len(jobs)} jobs",
            jobs=jobs,
            total_jobs=len(jobs)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
