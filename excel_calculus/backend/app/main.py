from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from excel_calculus.backend.app.database import engine, Base
from excel_calculus.backend.app.api import concerns, search, cases, assessment, reports, ingestion

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PV Safety Concern Evaluation Platform (Excel Calculus)",
    description="Deterministic Pharmacovigilance line-listing processing, MedDRA SMQ matching, case review, and PBRER Section 16.3 reporting.",
    version="1.0.0"
)

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(concerns.router)
app.include_router(search.router)
app.include_router(cases.router)
app.include_router(assessment.router)
app.include_router(reports.router)
app.include_router(ingestion.router)

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "PV Safety Concern Evaluation Platform",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("excel_calculus.backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
