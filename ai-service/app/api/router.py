from fastapi import APIRouter
from app.api.endpoints import waiter, recommendation

api_router = APIRouter()

api_router.include_router(waiter.router)
api_router.include_router(recommendation.router)
