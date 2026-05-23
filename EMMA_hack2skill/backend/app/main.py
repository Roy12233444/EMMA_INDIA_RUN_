from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import ws_terminal
from app.config import settings
import logging

# Configure main app logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")

app = FastAPI(
    title="EMMA Backend Server",
    description="Enterprise Metacognitive Multi-Agent Fleet backend core.",
    version="1.0.0"
)

# Set up CORS middleware to support local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in development
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all HTTP headers
)

# Register routers
app.include_router(ws_terminal.router, tags=["WebSocket"])

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
