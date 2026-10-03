from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.management import router as management_router
from app.api.routes.mapping_assistant import router as mapping_assistant_router
from app.api.routes.quality import router as quality_router
from app.api.routes.logistics import router as logistics_router


app = FastAPI(
    title="Predictive Logistics API",
    version="1.0.0",
)


app.include_router(auth_router)
app.include_router(ingestion_router)
app.include_router(management_router)
app.include_router(mapping_assistant_router)
app.include_router(quality_router)
app.include_router(logistics_router)


@app.get("/")
def root():
    return {
        "message": "Predictive Logistics API is running",
        "version": "1.0.0",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }