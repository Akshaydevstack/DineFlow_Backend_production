from fastapi import APIRouter, Header, HTTPException
from app.schemas.waiter import WaiterRequest
from app.services.waiter_service import run_waiter_agent
from app.core.exceptions import ResourceExhaustedException, AIServiceException

router = APIRouter()


@router.post("/ai-waiter/")
async def ai_waiter_endpoint(
    payload: WaiterRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_restaurant_id: str = Header(..., alias="X-Restaurant-Id"),
    x_table_id: str = Header(..., alias="X-Table-Id"),
):
    try:
        result = await run_waiter_agent(
            user_id=x_user_id,
            restaurant_id=x_restaurant_id,
            table_public_id=x_table_id,
            message=payload.message,
            latitude=payload.latitude,
            longitude=payload.longitude
        )
        return result
    except ResourceExhaustedException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except AIServiceException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
