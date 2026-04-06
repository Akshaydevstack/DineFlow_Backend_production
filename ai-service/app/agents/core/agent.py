import os
import json
import re
from datetime import datetime
import concurrent.futures
from loguru import logger

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from app.agents.tools.rag_tools import tool_search_menu, tool_get_past_orders
from app.agents.tools.cart_tools import cart_add, cart_update, cart_remove, cart_clear, cart_view
from app.agents.tools.order_tools import place_order, cancel_order
from app.agents.tools.restaurant_tools import tool_check_table_availability, tool_get_restaurant_info
from app.agents.tools.recommendation_tools import tool_get_personalized_recommendations
from app.agents.core.memory import get_session, save_session
from app.agents.tools.email_tools import tool_send_receipt, tool_send_feedback

# ✅ Import DB fetchers for real-time context injection
from app.db.pgvector_client import get_restaurant_metadata, get_table_metadata, get_user_metadata


TOOLS = [
    tool_search_menu,
    tool_get_past_orders,
    tool_get_personalized_recommendations,
    tool_get_restaurant_info,
    tool_check_table_availability,
    cart_add,
    cart_update,
    cart_remove,
    cart_clear,
    cart_view,
    place_order,
    cancel_order,
    tool_send_receipt,
    tool_send_feedback
]


SYSTEM_PROMPT = """\
You are Dina, a warm, attentive, and highly professional AI Waiter at {restaurant_name}.
Your goal is to provide a seamless, conversational, and delightful dining experience.

🕐 Current Time: {current_time}
📍 Restaurant Status: {restaurant_status}
🪑 Guest Location: Table {table_number} in the {zone_name}

━━━ TONE, PERSONA & FORMATTING ━━━
- ALWAYS SPEAK: You MUST always provide a text response. NEVER return an empty or blank message. Even if the UI is handling the display, you must provide a conversational sentence.
- INITIAL GREETING ONLY: Greet the guest appropriately based on the time ONLY in your very first message. Do NOT start subsequent replies with greetings like "Good morning", "Hello", or "Welcome".
- PERSONALIZATION: You have access to the user's details in the SESSION CONTEXT under [USER PROFILE DETAILS]. Use their name naturally in conversation. If they ask "who am I" or ask about their account, tell them their details cheerfully.
- Be conversational, polite, and hospitable. Keep replies very concise.
- NEVER expose backend mechanics. Do not mention "tools", "dish_ids", or "databases".
- MANDATORY FORMATTING: NEVER use line breaks (\n), newlines, or bullet points.
- NO STALLING: NEVER say "I am fetching it", "Let me check", or "One moment". Call tools and IMMEDIATELY provide the final answer.

━━━ CRITICAL UI RULE: THE HANDOFF (TOP & BOTTOM TEXT) ━━━
- The frontend UI renders visual cards for the Menu, Cart, and Orders ONLY when you use the `|||` delimiter.
- WHEN SHOWING ITEMS (Menu, Cart with items, Past Orders, Order Receipts): You MUST separate your introductory sentence from your follow-up question using the `|||` delimiter.
- IF A TOOL RETURNS EMPTY (e.g., empty cart, no past orders): DO NOT use the `|||` delimiter. Reply normally.
- EXAMPLES OF GOOD RESPONSES: 
  [Menu] "Here are some spicy options you might like! ||| Do any of these catch your eye?" 
  [Full Cart] "Here is your current cart. ||| Would you like to proceed to checkout?"
  [Empty Cart] "Your cart is currently empty. What would you like to add today?" (DO NOT USE DELIMITER)
  [Past Orders] "Here is your order history, {user_name}. ||| Is there a specific order you'd like to reorder or cancel?"
  [Placed Order] "Your order has been placed successfully! ||| Would you like to see our dessert menu?"

━━━ THE DINEFLOW LOGIC ━━━
1. DISCOVERY & MENU
   - Call tool_search_menu for cravings/menu questions.
   - Call tool_get_personalized_recommendations for "What's good?".
   - Call tool_get_past_orders if they ask about previous visits. (For "last order", pass limit=1).

2. CART & CHECKOUT (STRICT RULES)
   - ADDING ITEMS (NO GUESSING): If a user generally asks for food (e.g., "I want pizza", "add a burger", "get me coffee"), DO NOT call `cart_add`. You MUST call `tool_search_menu` to display the options and tell the user to click the "+ Add to Cart" button on the dish they want.
   - EXECUTING EXPLICIT ACTIONS: ONLY call `cart_add`, `cart_update`, or `cart_remove` if the user specifies the EXACT dish name (this happens when they click the UI buttons, e.g., "Add Spicy Paneer Pizza to my cart").
   - FINDING IDS & DATA: Look at the SESSION CONTEXT (last_search_results) to find the `dish_id`. NEVER read dish details from the menu (RAG) when discussing the cart. ALWAYS rely exclusively on the data returned by the cart tools.
   - AVOID REDUNDANT DISPLAYS & DOUBLE CALLS: The `cart_add`, `cart_update`, and `cart_remove` tools automatically return the updated cart. DO NOT call `cart_view` or `tool_search_menu` in the same response. DO NOT say "Here is your cart" after modifying the cart; simply confirm the action (e.g., "I've added another one!").
   - CHECKOUT TRANSITION: If the user explicitly asks to "place the order" or "checkout", DO NOT show or review the cart again. Immediately proceed to the checkout/payment step.
   - DELIMITER EXCLUSIVITY: Whenever you modify or view the cart, the UI renders the Cart Card automatically. You MUST use the `|||` delimiter.
     [CORRECT] "Here is the menu. ||| Please click 'Add to Cart' on the dish you'd like!"
     [CORRECT] "I've added it to your cart. ||| Would you like to proceed to checkout?"

3. EMAIL RECEIPTS (STRICT RULES)
   - If a user asks to email their order details, bill, or receipt, you MUST call `tool_send_receipt`.
   - NEW ORDER REQUIREMENT: If you JUST placed the order using `place_order`, you MUST pass the exact JSON output from `place_order` into the `recent_order_json` parameter!
   - REQUIRED DATA: `email_address`, `order_id`, and `recent_order_json` (if new). 
   - Check the SESSION CONTEXT under [USER PROFILE DETAILS] for their Email. If it exists and is not 'Unknown', use it automatically. Do NOT ask the user for their email if it is already in the context.

4. ORDER CANCELLATION
   - First check SESSION CONTEXT for recent_order_ids 
   - Confirm intent ("Are you sure you want to cancel?"), then call cancel_order.

5. FEEDBACK & COMPLAINTS (STRICT RULES)
   - STEP 1 (GATHER INFO): If a user says they want to leave feedback, DO NOT automatically apologize—feedback can be positive! 
     * If they explicitly state a complaint: Apologize, validate their feelings, and ask for details.
     * If they just say "I want to leave feedback" or "I have a suggestion": Warmly ask them what they'd like to share (e.g., "I'd love to hear your thoughts! What would you like to pass along to the manager?").
     * Do NOT call the tool during this step.
   - STEP 2 (EXECUTE): ONLY AFTER the user replies with the actual details of their experience, call `tool_send_feedback` using their detailed explanation as the `message`.
   - NO HALLUCINATIONS: NEVER say "I have sent your feedback" or "I am sending it now" until you have successfully executed the `tool_send_feedback` tool.
   - REQUIRED DATA: `user_id`, `restaurant_id`, `user_name`, `user_email`, `feedback_type`, and `message`. 
   - MISSING DATA: Pull the user_id, name, and email from the [USER PROFILE DETAILS]. If 'Unknown', you must also ask the user for their name and email before sending.

━━━ SESSION CONTEXT ━━━
{context}
"""


def _build_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.2,
        max_output_tokens=1024,
    )


def _format_context(user_id: str, restaurant_id: str, session: dict, user_meta: dict) -> str:
    lines = [
        f"user_id: {user_id}",
        f"restaurant_id: {restaurant_id}",
    ]

    # ✅ Inject full user details block so the AI knows everything!
    lines.append("\n[USER PROFILE DETAILS]")
    if user_meta:
        lines.append(f"Name: {user_meta.get('name', 'Guest')}")
        lines.append(f"Email: {user_meta.get('email', 'Unknown')}")
        if user_meta.get("mobile_number"):
            lines.append(f"Phone: {user_meta.get('mobile_number')}")
        if user_meta.get("role"):
            lines.append(f"Role: {user_meta.get('role')}")
        if user_meta.get("created_at"):
            lines.append(f"Member Since: {user_meta.get('created_at')}")
    else:
        lines.append("Name: Guest")
        lines.append("Email: Unknown")

    lines.append("\n[SESSION DATA]")
    if session.get("table_public_id"):
        lines.append(f"table_public_id: {session['table_public_id']}")

    if session.get("last_search_results"):
        lines.append("last_search_results (dish_ids for cart):")
        for r in session["last_search_results"][:5]:
            lines.append(
                f"  - {r.get('name', '?')} → dish_id: {r.get('dish_id', '?')}")

    if session.get("recent_order_ids"):
        lines.append(
            "recent_order_ids (use for cancellation, most recent first):")
        for entry in session["recent_order_ids"][:3]:
            lines.append(
                f"  - order_id: {entry.get('order_id')} | "
                f"items: {entry.get('items', '?')} | "
                f"date: {entry.get('date', '?')}"
            )

    return "\n".join(lines)


def _extract_tools_and_results(messages: list) -> dict:
    extracted = {
        "tools_used": [],
        "dishes": [],
        "cart": [],
        "past_orders": [],
        "current_order": None
    }

    for msg in messages:
        # 1. Capture tools used
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                extracted["tools_used"].append(tc.get("name"))

        tool_name = getattr(msg, "name", "")
        content = str(getattr(msg, "content", ""))

        # 2. Capture Dishes
        if tool_name in ["tool_search_menu", "tool_get_personalized_recommendations"] and content:
            current_dish = None
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue

                if line.startswith("- "):
                    if current_dish:
                        extracted["dishes"].append(current_dish)

                    current_dish = {}
                    parts = [p.strip() for p in line.split("|")]
                    current_dish["name"] = parts[0].replace(
                        "- ", "").replace("**", "").strip()

                    for part in parts[1:]:
                        if "₹" in part:
                            current_dish["price"] = part.replace(
                                "₹", "").strip()
                        elif "Available" in part or "Unavailable" in part:
                            current_dish["available"] = "✅" in part
                        elif "Prep:" in part:
                            current_dish["prep_time"] = part.replace(
                                "Prep:", "").strip()
                        elif "dish_id:" in part:
                            current_dish["dish_id"] = part.replace(
                                "dish_id:", "").strip()
                        elif "image:" in part:
                            current_dish["image"] = part.replace(
                                "image:", "").strip()

                elif current_dish is not None:
                    if line.startswith("Description:"):
                        current_dish["description"] = line.replace(
                            "Description:", "").strip()
                    elif line.startswith("Tags:"):
                        tags_part = line.split("|")[0].replace(
                            "Tags:", "").strip()
                        current_dish["tags"] = [t.strip()
                                                for t in tags_part.split(",") if t.strip()]
                        if "Allergens:" in line:
                            allergens_part = line.split(
                                "Allergens:")[-1].strip()
                            current_dish["allergens"] = [
                                a.strip() for a in allergens_part.split(",") if a.strip()]
                    elif line.startswith("Allergens:") and "Tags:" not in line:
                        allergens_part = line.replace("Allergens:", "").strip()
                        current_dish["allergens"] = [
                            a.strip() for a in allergens_part.split(",") if a.strip()]

            if current_dish:
                extracted["dishes"].append(current_dish)

        # 3. Capture Cart Data
        if tool_name in ["cart_view", "cart_add", "cart_update", "cart_remove", "cart_clear"] and content:
            try:
                cart_data = json.loads(content)
                if isinstance(cart_data, list):
                    extracted["cart"] = cart_data
                elif isinstance(cart_data, dict) and "items" in cart_data:
                    extracted["cart"] = cart_data["items"]
                elif isinstance(cart_data, dict) and "cart" in cart_data:
                    extracted["cart"] = cart_data["cart"]
            except json.JSONDecodeError:
                pass

        # ✅ 4. Capture Past Orders (Fixed to parse clean JSON)
        if tool_name == "tool_get_past_orders" and content:
            try:
                orders_data = json.loads(content)
                if isinstance(orders_data, list):
                    extracted["past_orders"] = orders_data
            except json.JSONDecodeError:
                pass

        # 5. Capture NEWLY Placed Order
        if tool_name == "place_order" and content:
            try:
                order_data = json.loads(content)
                extracted["current_order"] = {
                    "order_id": order_data.get("order_id"),
                    "status": order_data.get("status", "RECEIVED"),
                    "total": order_data.get("total"),
                    "items": order_data.get("items", [])
                }
                extracted["cart"] = []
            except json.JSONDecodeError:
                order_match = re.search(r'ORD-[A-Z0-9]+', content)
                if order_match:
                    extracted["current_order"] = {
                        "order_id": order_match.group(0),
                        "status": "RECEIVED"
                    }
                    extracted["cart"] = []

    # ✅ THE NEW UI CLUTTER FAILSAFE
    # If the AI modified or viewed the cart, suppress the 'dishes' array so the UI ONLY renders the Cart card!
    cart_tools = ["cart_view", "cart_add", "cart_update",
                  "cart_remove", "cart_clear", "place_order"]
    if extracted["cart"] or extracted["current_order"]:
        if any(t in extracted["tools_used"] for t in cart_tools):
            extracted["dishes"] = []

    return extracted


def _safe_content(content) -> str:
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    return str(content).strip()


def run_agent(
    user_id: str,
    restaurant_id: str,
    table_public_id: str,
    message: str,
) -> dict:
    session = get_session(user_id, restaurant_id)
    session["table_public_id"] = table_public_id

    # ⚡ OPTIMIZATION: Check Memory Cache first!
    # ✅ FIX: Checking if the keys are populated, preventing an empty {} from persisting!
    if not session.get("cached_user_meta") or not session.get("cached_rest_meta"):
        # Fetch live metadata in PARALLEL (Takes 1/3rd of the time)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_rest = executor.submit(get_restaurant_metadata, restaurant_id)
            future_table = executor.submit(get_table_metadata, table_public_id, restaurant_id)
            future_user = executor.submit(get_user_metadata, user_id)

            rest_meta = future_rest.result() or {}
            table_meta = future_table.result() or {}
            user_meta = future_user.result() or {}
            
        # Cache it for the next message!
        session["cached_rest_meta"] = rest_meta
        session["cached_user_meta"] = user_meta
    else:
        # ⚡ Lightning fast memory lookup
        rest_meta = session["cached_rest_meta"]
        user_meta = session["cached_user_meta"]
        # Tables might change (occupied/vacant), so we still fetch that one
        table_meta = get_table_metadata(table_public_id, restaurant_id) or {}


    rest_name = rest_meta.get("name", "our restaurant")
    rest_status = "OPEN" if rest_meta.get("is_open") else "CLOSED"
    table_num = table_meta.get("table_number", "Unknown")
    zone_name = table_meta.get("zone_name", "Main Dining Area")

    # 2. Current time formatting
    now = datetime.now()
    current_time_str = now.strftime("%A, %b %d, %Y · %I:%M %p")

    # 3. Rebuild chat history
    raw_messages = session.get("messages", [])
    chat_history: list = []
    for m in raw_messages:
        if m["role"] == "user":
            chat_history.append(HumanMessage(content=m["content"]))
        else:
            chat_history.append(AIMessage(content=m["content"]))

    # 4. Inject dynamic system prompt with real-time data
    user_name = user_meta.get("name", "Guest") if user_meta else "Guest"
    context_str = _format_context(user_id, restaurant_id, session, user_meta)

    # Note: Passing user_name to dynamic_system_prompt so EXAMPLES format correctly 
    dynamic_system_prompt = SYSTEM_PROMPT.format(
        restaurant_name=rest_name,
        restaurant_status=rest_status,
        table_number=table_num,
        zone_name=zone_name,
        current_time=current_time_str,
        context=context_str,
        user_name=user_name 
    )

    # 5. Build and run agent
    llm = _build_llm()
    agent_executor = create_react_agent(
        llm,
        TOOLS,
        prompt=SystemMessage(content=dynamic_system_prompt),
    )

    chat_history.append(HumanMessage(content=message))

    try:
        result = agent_executor.invoke({"messages": chat_history})
        raw_final_message = _safe_content(result["messages"][-1].content)
        extracted_data = _extract_tools_and_results(result["messages"])

    except Exception as e:
        logger.exception(f"Agent error | user={user_id} | {e}")
        return {
            "response":   "I hit a small snag — could you try that again?",
            "bottom_text": None,
            "tools_used": [],
        }

    # ✅ Split the text into Top and Bottom based on the delimiter
    parts = raw_final_message.split("|||")
    top_text = parts[0].strip()
    bottom_text = parts[1].strip() if len(parts) > 1 else None

    # 👇 FIXED FAILSAFE: If the AI forgot the top text (e.g. it just output "||| Checkout?"), force it!
    if not top_text:
        tools_used = extracted_data.get("tools_used", [])
        if any("cart" in t for t in tools_used):
            top_text = "Here is your cart."
        elif "place_order" in tools_used:
            top_text = "I have processed your order."
        elif "tool_search_menu" in tools_used:
            top_text = "Here are some options for you."
        elif "tool_get_past_orders" in tools_used:
            top_text = "Here are your past orders."
        else:
            top_text = "Here is what you asked for."

    # Clean the message for the chat history
    clean_history_message = top_text
    if bottom_text:
        clean_history_message += f" {bottom_text}"

    # 6. Persist session
    raw_messages.append({"role": "user",      "content": message})
    raw_messages.append(
        {"role": "assistant", "content": clean_history_message})
    session["messages"] = raw_messages[-20:]

    # Update recent search context
    if extracted_data["dishes"]:
        session["last_search_results"] = extracted_data["dishes"]

    # Maintain list of recent order IDs for cancellations
    if extracted_data["past_orders"]:
        existing = session.get("recent_order_ids", [])
        existing_ids = {e.get("order_id") for e in existing if isinstance(e, dict)}
        for o in extracted_data["past_orders"]:
            if isinstance(o, dict) and o.get("order_id") not in existing_ids:
                existing.insert(0, o)
        session["recent_order_ids"] = existing[:5]

    save_session(user_id, restaurant_id, session)

    # ✅ Pass the separated text to the frontend!
    return {
        "response": top_text,
        "bottom_text": bottom_text,
        "tools_used": extracted_data["tools_used"],
        "dishes": extracted_data["dishes"],
        "cart": extracted_data["cart"],
        "past_orders": extracted_data["past_orders"],
        "current_order": extracted_data["current_order"],
    }