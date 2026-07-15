from fastapi import APIRouter, Header
from app.schemas.recommendation import TrackViewRequest
from app.services import recommendation_service

router = APIRouter()


@router.post("/track-view/")
async def track_view(
    payload: TrackViewRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_restaurant_id: str = Header(..., alias="X-Restaurant-Id")
):
    await recommendation_service.track_dish_view(x_user_id, payload.dish, x_restaurant_id)
    return {"message": "view tracked"}


@router.get("/recommendations/")
async def get_recommendations(
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_restaurant_id: str = Header(..., alias="X-Restaurant-Id")
):
    return await recommendation_service.get_recommendations(x_user_id, x_restaurant_id)
