from fastapi import FastAPI

app = FastAPI(
    title="Predictive Logistics API",
    description="Backend API for the Predictive Logistics & Forward Supply Chain platform.",
    version="0.1.0",
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