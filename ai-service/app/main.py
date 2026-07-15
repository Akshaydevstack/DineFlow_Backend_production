import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core import config
from app.api.router import api_router

# 1. Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up DineFlow AI Service...")
    yield 
    logger.info("Shutting down DineFlow AI Service...")

app = FastAPI(
    title="DineFlow AI Service",
    version="1.0.0",
    root_path="/api/ai",
    lifespan=lifespan,
    docs_url=None if config.IS_PRODUCTION else "/docs",
    redoc_url=None if config.IS_PRODUCTION else "/redoc",
)

# 5. GZip Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 6. Global Exception Handler
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

app.include_router(api_router)