#Actively in Use

from fastapi import APIRouter
import time

router = APIRouter()

@router.get("/", summary="Health Check")
async def health_check():
    return {
        "status": "ok",
        "uptime": time.time()
    }

@router.get("/metrics", summary="Prometheus Metrics")
async def metrics():
    # In Phase 5, replace with real Prometheus client
    return {
        "workflows_active": 0,
        "workflows_failed": 0,
        "queue_depth": 0
    }
