from pydantic import BaseModel
from typing import Dict, Any

class TrackViewRequest(BaseModel):
    dish: Dict[str, Any]
