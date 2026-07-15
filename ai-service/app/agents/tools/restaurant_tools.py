from langchain_core.tools import tool
from app.repositories.db.pgvector import get_restaurant_profile_db, check_table_availability_db

@tool
def tool_get_restaurant_info(restaurant_id: str) -> str:
    """
    Use this tool to answer questions about the restaurant itself.
    This includes opening hours, closing time, exact location, phone number, email, and available zones.
    Always pass the restaurant_id found in your SESSION CONTEXT.
    """
    profile = get_restaurant_profile_db(restaurant_id)
    return profile


@tool
def tool_check_table_availability(restaurant_id: str, zone_name: str = "") -> str:
    """
    CRITICAL: You MUST use this tool EVERY SINGLE TIME a user asks about table availability, 
    even if they ask about a specific table (e.g. "Is T-01 free?") or if you checked it previously.
    NEVER guess or rely on chat history, because table statuses change in real-time.
    
    If the user asks for a specific zone (like "VIP" or "Outdoor"), pass it as 'zone_name'.
    If they just ask "what tables are free?", leave zone_name empty to get all tables.
    Always pass the restaurant_id found in your SESSION CONTEXT.
    """
    tables = check_table_availability_db(restaurant_id, zone_name if zone_name else None)
    
    if not tables:
        return "No tables found for that criteria."

    response = "Here is the current table status:\n"
    
    for t in tables:
        if isinstance(t, dict):
            is_occupied = t.get("is_occupied", False)
            is_reserved = t.get("is_reserved_manual", False)
            
            if is_occupied:
                status = "Occupied"
            elif is_reserved:
                status = "Not available (Reserved for a person)"
            else:
                status = "Available"
                
            response += f"- Table {t.get('table_number')} ({t.get('zone_name', 'Dining')}): {status}\n"
        else:
            response += f"- {t}\n"
            
    return response