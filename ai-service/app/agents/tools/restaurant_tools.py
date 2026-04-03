from langchain_core.tools import tool
from app.db.pgvector_client import get_restaurant_profile_db, check_table_availability_db

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
    Use this tool when a user asks about moving tables, seating capacity, or if tables are available in other areas/zones.
    If the user asks for a specific zone (like "AC Room" or "Outdoor"), pass it as 'zone_name'.
    If they just ask "what tables are free?", leave zone_name empty to get all tables.
    Always pass the restaurant_id found in your SESSION CONTEXT.
    """
    tables = check_table_availability_db(restaurant_id, zone_name if zone_name else None)
    
    if not tables:
        return f"No tables found for that criteria."

    # Return a formatted list of all tables and their current status
    response = "Here is the current table status:\n"
    for t in tables:
        response += f"- {t}\n"
        
    return response