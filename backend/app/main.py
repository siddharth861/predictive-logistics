from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.db.session import engine


app = FastAPI(
    title="Predictive Logistics API",
    description="Backend API for the Predictive Logistics & Forward Supply Chain platform.",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Predictive Logistics API is running",
        "version": "0.1.0",
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "backend",
    }


@app.get("/api/health/database")
def database_health_check():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "status": "ok",
        "database": "postgresql",
    }