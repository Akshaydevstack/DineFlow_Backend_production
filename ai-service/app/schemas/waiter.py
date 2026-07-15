from pydantic import BaseModel
from typing import Optional

class WaiterRequest(BaseModel):
    message: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
