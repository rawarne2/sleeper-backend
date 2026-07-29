from fastapi import APIRouter
from fastapi.responses import JSONResponse

from managers.database_manager import DatabaseManager
from utils.datetime_serialization import utc_now_rfc3339
from utils.helpers import setup_logging

router = APIRouter(prefix="/api", tags=["Health"])
logger = setup_logging(__name__)


@router.get("/ktc/health", summary="Check API and database health status")
def health_check():
    """Verify API process and database connectivity."""
    try:
        logger.info("Performing health check...")
        connection_ok = DatabaseManager.verify_database_connection()
        timestamp = utc_now_rfc3339()
        if not connection_ok:
            return JSONResponse(
                {"status": "unhealthy", "database": "connection_failed",
                 "timestamp": timestamp},
                status_code=500)
        return {"status": "healthy", "database": "connected", "timestamp": timestamp}
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return JSONResponse(
            {"status": "unhealthy", "database": "error", "error": str(e),
             "timestamp": utc_now_rfc3339()}, status_code=500)
