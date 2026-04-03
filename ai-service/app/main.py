import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from app.routers import views

# 1. Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. Lifespan context manager (replaces old startup/shutdown events)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP LOGIC ---
    logger.info("Starting up DineFlow AI Service...")
    # e.g., Load ML models, initialize database connection pools here
    
    yield # App runs and serves requests here
    
    # --- SHUTDOWN LOGIC ---
    logger.info("Shutting down DineFlow AI Service...")
    # e.g., Clean up DB connections, clear memory here

# 3. Determine environment to secure API Docs
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
is_production = ENVIRONMENT == "production"

app = FastAPI(
    title="DineFlow AI Service",
    version="1.0.0",
    root_path="/api/ai",
    lifespan=lifespan,
    # Disable Swagger/ReDoc UIs in production for security, 
    # or keep them if you need external developers to see them.
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
)


# 5. GZip Middleware (Compresses responses to save bandwidth)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 6. Global Exception Handler (Prevents raw tracebacks from leaking to users)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
    )

@app.get("/")
def root():
    return {"message": "DineFlow AI Service Running"}

@app.get("/health/")
def health():
    return {"status": "ok"}

app.include_router(views.router)