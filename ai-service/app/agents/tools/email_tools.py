import os
import smtplib
import re 
import threading
import json 
import ast          
from typing import Any  
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from langchain_core.tools import tool
from loguru import logger


from app.db.pgvector_client import (
    get_order_metadata, 
    get_restaurant_metadata, 
    get_restaurant_profile_db,
    get_user_metadata  
)


def _format_friendly_date(iso_date_str: str) -> str:
    """Converts a raw ISO timestamp into a clean, human-readable format."""
    if not iso_date_str or iso_date_str == "Unknown Date":
        return "Unknown Date"
    try:
        dt = datetime.fromisoformat(iso_date_str)
        return dt.strftime("%B %d, %Y at %I:%M %p")
    except Exception:
        return iso_date_str 


def _send_email_background(msg, smtp_server, smtp_port, sender_email, sender_password, success_log):
    """
    Connects to the SMTP server and sends the email. 
    Runs in a separate thread so it doesn't block the AI or the Frontend!
    """
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        logger.info(success_log)
    except Exception as e:
        logger.error(f"Background Email Task Failed: {e}")


@tool
def tool_send_receipt(user_id: str, restaurant_id: str, email_address: str, order_id: str, recent_order_json: Any = None) -> str:
    """
    Sends an order receipt or bill to the user's email address.
    CRITICAL: If you just placed this order using `place_order`, you MUST pass the exact JSON string or object output 
    from `place_order` into the `recent_order_json` parameter. If it's an older order, leave it blank.
    """
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    sender_email = os.getenv("SMTP_USERNAME")    
    sender_password = os.getenv("SMTP_PASSWORD") 

    if not sender_email or not sender_password:
        logger.error("SMTP credentials are missing from environment variables.")
        return "Failed to send email. Tell the user the email system is currently unconfigured."

    # 1. Bulletproof parsing of the AI's provided JSON
    order_meta = None
    if recent_order_json:
        if isinstance(recent_order_json, dict):
            order_meta = recent_order_json
        elif isinstance(recent_order_json, str):
            cleaned = recent_order_json.strip()
            # Remove markdown backticks if the LLM added them
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:-3].strip()
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:-3].strip()
                
            try:
                order_meta = json.loads(cleaned)
            except json.JSONDecodeError:
                try:
                    # Fallback if the AI passed a stringified Python dict (using single quotes)
                    order_meta = ast.literal_eval(cleaned)
                except Exception as e:
                    logger.warning(f"Failed to parse recent_order_json fallback: {e}")

        # Unwrap the 'order' key if the backend nested it!
        if order_meta and "order" in order_meta and isinstance(order_meta["order"], dict):
            order_meta = order_meta["order"]

    # 2. If parsing failed OR the items are missing, fallback to the Database
    if not order_meta or not order_meta.get("items"):
        db_meta = get_order_metadata(order_id, restaurant_id)
        if db_meta:
            # Unwrap the DB response just in case it is also nested
            if "order" in db_meta and isinstance(db_meta["order"], dict):
                db_meta = db_meta["order"]
                
            if db_meta.get("items"):
                order_meta = db_meta

    # 3. CRITICAL FAIL-SAFE: Prevent blank emails!
    if not order_meta or not order_meta.get("items"):
        logger.error(f"Order {order_id} lacks items or wasn't found in sync.")
        return f"Could not retrieve the item details for {order_id} yet. The system is still syncing the order. Please ask the user to wait a few seconds and try again."

    # 4. Extract Financials & Data
    total = order_meta.get("total", "0.00")
    subtotal = order_meta.get("subtotal", order_meta.get("total", "0.00")) # Fallback to total if missing
    tax = order_meta.get("tax", "0.00")
    discount = order_meta.get("discount", "0.00")
    
    raw_date = order_meta.get("date", order_meta.get("created_at", datetime.now().isoformat()))
    formatted_date = _format_friendly_date(raw_date)
    status = order_meta.get("status", "RECEIVED")
    short_id = order_id[-8:] if len(order_id) > 8 else order_id
    special_request = order_meta.get("special_request", "")
    table_num = order_meta.get("table_number", "")

    # 5. Build the HTML Table Rows for Items (Mobile-Optimized Layout)
    items = order_meta.get("items", [])
    items_html = ""
    
    for item in items:
        name = item.get("name", item.get("dish_name", "Item"))
        qty = item.get("quantity", 1)
        price = item.get("total", item.get("total_price", item.get("unit_price", item.get("price", "0.00"))))
        
        # Grab image or use a sleek fallback
        image_url = item.get("image", "https://res.cloudinary.com/dxsimc9dz/image/upload/v1738734327/placeholder.jpg")
        
        items_html += f"""
        <tr>
            <td style="padding: 12px 0; border-bottom: 1px solid #f1f5f9; width: 55px; vertical-align: top;">
                <img src="{image_url}" alt="{name}" style="width: 46px; height: 46px; border-radius: 8px; object-fit: cover; display: block; background-color: #f8fafc; border: 1px solid #e2e8f0;" />
            </td>
            <td style="padding: 12px 10px; border-bottom: 1px solid #f1f5f9; vertical-align: top;">
                <div style="color: #1e293b; font-weight: 600; font-size: 14px; line-height: 1.4;">{name}</div>
                <div style="color: #64748b; font-size: 13px; margin-top: 4px; font-weight: 500;">Qty: {qty}</div>
            </td>
            <td style="padding: 12px 0; border-bottom: 1px solid #f1f5f9; color: #0f172a; text-align: right; font-weight: 600; font-size: 15px; vertical-align: top;">
                ₹{price}
            </td>
        </tr>
        """

    # Add Special Request Row if exists
    special_request_html = ""
    if special_request and special_request.strip() != "":
        special_request_html = f"""
        <tr>
            <td colspan="3" style="padding: 16px; background-color: #fffbeb; border-radius: 8px; margin-top: 15px; border-left: 4px solid #f59e0b; display: block;">
                <p style="margin: 0; color: #92400e; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Special Request</p>
                <p style="margin: 6px 0 0 0; color: #b45309; font-size: 14px; font-style: italic;">"{special_request}"</p>
            </td>
        </tr>
        """
        
    table_html = f" | Table: {table_num}" if table_num else ""

    # 6. Build the Full HTML Template with Responsive Styles
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Order Receipt</title>
        <style>
            @media only screen and (max-width: 600px) {{
                .main-wrapper {{ padding: 20px 10px !important; }}
                .content-box {{ padding: 24px 15px !important; }}
                .header-box {{ padding: 30px 20px !important; }}
                .title-text {{ font-size: 24px !important; }}
                .total-amount {{ font-size: 20px !important; }}
            }}
        </style>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f8fafc;">
            <tr>
                <td align="center" class="main-wrapper" style="padding: 40px 20px;">
                    <table width="100%" style="max-width: 550px; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03); overflow: hidden;" cellpadding="0" cellspacing="0">
                        <tr>
                            <td class="header-box" style="background: linear-gradient(135deg, #6366f1, #8b5cf6); padding: 40px 30px; text-align: center;">
                                <h1 class="title-text" style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 700; letter-spacing: -0.5px;">DineFlow</h1>
                                <p style="color: #e0e7ff; margin: 8px 0 0 0; font-size: 15px; font-weight: 500;">Order Receipt</p>
                            </td>
                        </tr>
                        <tr>
                            <td class="content-box" style="padding: 30px;">
                                <table width="100%" cellpadding="0" cellspacing="0">
                                    <tr>
                                        <td style="padding-bottom: 20px; width: 50%;">
                                            <p style="margin: 0 0 4px 0; color: #64748b; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Order ID</p>
                                            <p style="margin: 0; color: #0f172a; font-weight: 600; font-size: 15px;">#{short_id}</p>
                                        </td>
                                        <td style="padding-bottom: 20px; width: 50%; text-align: right;">
                                            <p style="margin: 0 0 4px 0; color: #64748b; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Date</p>
                                            <p style="margin: 0; color: #0f172a; font-weight: 500; font-size: 14px;">{formatted_date}</p>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td colspan="2" style="padding-bottom: 24px; border-bottom: 2px dashed #e2e8f0;">
                                            <span style="display: inline-block; background-color: #f1f5f9; color: #475569; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 700; letter-spacing: 0.5px;">
                                                STATUS: {status}{table_html}
                                            </span>
                                        </td>
                                    </tr>
                                </table>
                                
                                <table width="100%" cellpadding="0" cellspacing="0" style="margin-top: 15px; margin-bottom: 15px;">
                                    {items_html}
                                </table>
                                
                                {special_request_html}

                                <table width="100%" cellpadding="0" cellspacing="0" style="margin-top: 20px; border-top: 2px dashed #e2e8f0; padding-top: 15px;">
                                    <tr>
                                        <td style="padding: 6px 0; text-align: right; font-size: 14px; color: #64748b;">Subtotal</td>
                                        <td style="padding: 6px 0; text-align: right; font-size: 14px; color: #475569; font-weight: 600; width: 100px;">₹{subtotal}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 6px 0; text-align: right; font-size: 14px; color: #64748b;">Tax</td>
                                        <td style="padding: 6px 0; text-align: right; font-size: 14px; color: #475569; font-weight: 600;">₹{tax}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 6px 0; text-align: right; font-size: 14px; color: #10b981;">Discount</td>
                                        <td style="padding: 6px 0; text-align: right; font-size: 14px; color: #10b981; font-weight: 600;">-₹{discount}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding-top: 16px; text-align: right; font-size: 16px; color: #0f172a; font-weight: 700;">Total Amount</td>
                                        <td class="total-amount" style="padding-top: 16px; text-align: right; font-size: 24px; font-weight: 800; color: #6366f1;">₹{total}</td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    # 7. Setup the Multipart Email
    subject = f"Your Receipt from DineFlow (Order #{short_id})"
    msg = MIMEMultipart('alternative')
    msg['From'] = sender_email
    msg['To'] = email_address
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html'))

    # 8. Send Email in the Background
    success_log = f"HTML Receipt for {order_id} sent to {email_address}"
    threading.Thread(
        target=_send_email_background,
        args=(msg, smtp_server, smtp_port, sender_email, sender_password, success_log)
    ).start()

    return f"Successfully initiated sending email receipt for order {order_id} to {email_address}."





@tool
def tool_send_feedback(user_id: str, restaurant_id: str, user_name: str, user_email: str, feedback_type: str, message: str) -> str:
    """
    Sends a customer's suggestion, feedback, or complaint directly to the restaurant admin's email.
    Use this when a user wants to leave a review, suggest a new dish, or complain about their experience.
    """
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    sender_email = os.getenv("SMTP_USERNAME")    
    sender_password = os.getenv("SMTP_PASSWORD") 

    if not sender_email or not sender_password:
        logger.error("SMTP credentials are missing. Cannot send feedback.")
        return "Failed to send feedback. Email system is currently unconfigured."

    # 1. FETCH USER CONTACT DETAILS (Phone Number)
    user_meta = get_user_metadata(user_id) or {}
    user_phone = user_meta.get("mobile_number", "Not provided")

    # 2. FETCH THE RESTAURANT'S EMAIL FROM THE DATABASE
    rest_meta = get_restaurant_metadata(restaurant_id) or {}
    restaurant_email = rest_meta.get("email")
    
    if not restaurant_email:
        profile_text = get_restaurant_profile_db(restaurant_id)
        email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', profile_text)
        if email_match:
            restaurant_email = email_match.group(0)

    # 3. SET DESTINATION 
    admin_email = restaurant_email or os.getenv("ADMIN_EMAIL", sender_email)

    subject = f"New Customer {feedback_type} from {user_name}"
    
    # 4. Build a clean HTML email for the admin
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: -apple-system, sans-serif; background-color: #f8fafc; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h2 style="color: #0f172a; margin-top: 0; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px;">
                New Customer {feedback_type}
            </h2>
            <div style="background-color: #f8fafc; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #e2e8f0;">
                <p style="color: #475569; font-size: 14px; margin: 4px 0;"><strong>Customer ID:</strong> <span style="color: #0f172a;">{user_id}</span></p>
                <p style="color: #475569; font-size: 14px; margin: 4px 0;"><strong>Customer Name:</strong> <span style="color: #0f172a;">{user_name}</span></p>
                <p style="color: #475569; font-size: 14px; margin: 4px 0;"><strong>Email Address:</strong> <span style="color: #0f172a;">{user_email}</span></p>
                <p style="color: #475569; font-size: 14px; margin: 4px 0;"><strong>Phone Number:</strong> <span style="color: #0f172a;">{user_phone}</span></p>
                <p style="color: #475569; font-size: 14px; margin: 4px 0;"><strong>Restaurant ID:</strong> <span style="color: #0f172a;">{restaurant_id}</span></p>
            </div>
            
            <div style="background-color: #f1f5f9; padding: 20px; border-radius: 8px;">
                <p style="margin: 0; color: #1e293b; font-size: 16px; line-height: 1.5; font-style: italic;">
                    "{message}"
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart('alternative')
    msg['From'] = sender_email
    msg['To'] = admin_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html'))

    # ✅ 5. Send Feedback Email in the Background!
    success_log = f"{feedback_type} from {user_name} sent to restaurant admin at {admin_email}"
    threading.Thread(
        target=_send_email_background,
        args=(msg, smtp_server, smtp_port, sender_email, sender_password, success_log)
    ).start()

    # Returns instantly to the LLM
    return f"Successfully initiated sending the {feedback_type.lower()} to the restaurant manager."