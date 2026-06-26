from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.routers import ws_terminal
from app.routers import manifold as manifold_router
from app.config import settings
import logging

# Configure main app logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    STARTUP  — Logs server ready state.
    SHUTDOWN — Executes WAL TRUNCATE checkpoint and closes SQLite thread-local handles.
    """
    logger.info("[EMMA] ANJANEYA Memory Protocol initialised. All pillars active.")
    yield
    # SHUTDOWN: flush WAL and close connections
    try:
        from app.database.session import checkpoint_wal, close_thread_local_conn
        checkpoint_wal()
        close_thread_local_conn()
        logger.info("[EMMA] WAL checkpoint (TRUNCATE) executed on shutdown.")
    except Exception as exc:
        logger.warning("[EMMA] Shutdown WAL checkpoint failed: %s", exc)


app = FastAPI(
    title="EMMA Backend Server",
    description="Enterprise Metacognitive Multi-Agent Fleet backend core.",
    version="1.0.0",
    lifespan=lifespan,
)

# Set up CORS middleware to support local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in development
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all HTTP headers
)

# Uniform validation error response envelope — matches ANJANEYA error contract
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        errors.append({
            "field":   " → ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type":    error["type"],
        })
    return JSONResponse(
        status_code=422,
        content={
            "error":   "VALIDATION_ERROR",
            "detail":  "One or more request fields failed schema validation.",
            "context": {"errors": errors},
        },
    )


# Register routers
app.include_router(ws_terminal.router, tags=["WebSocket"])
app.include_router(manifold_router.router, prefix="/manifold", tags=["Manifold"])

@app.get("/health")
async def health_check():
    """Simple status check to verify backend service viability."""
    logger.info("Health status requested.")
    return {
        "status": "healthy",
        "service": "EMMA Backend Core",
        "config": {
            "model": settings.LOCAL_LLM_MODEL,
            "port": settings.PORT
        }
    }

if __name__ == "__main__":
    import uvicorn
    # Start the server if main.py is run directly
    logger.info(f"Starting server on port {settings.PORT}...")
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
