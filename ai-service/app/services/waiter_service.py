import asyncio
from google.api_core.exceptions import ResourceExhausted
from app.agents.core.agent import run_agent
from app.core.exceptions import ResourceExhaustedException, AIServiceException

async def run_waiter_agent(
    user_id: str,
    restaurant_id: str,
    table_public_id: str,
    message: str,
    latitude: float = None,
    longitude: float = None
) -> dict:
    """Invokes the conversational AI Waiter agent and handles core rate limits."""
    try:
        result = await asyncio.to_thread(
            run_agent,
            user_id=user_id,
            restaurant_id=restaurant_id,
            table_public_id=table_public_id,
            message=message,
            latitude=latitude,
            longitude=longitude
        )
        return result
    except ResourceExhausted as e:
        raise ResourceExhaustedException() from e
    except Exception as e:
        raise AIServiceException("Something went wrong with the AI waiter.") from e
