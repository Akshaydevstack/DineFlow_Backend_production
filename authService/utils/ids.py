import uuid

def generate_unique_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"