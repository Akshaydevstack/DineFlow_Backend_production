import os
import firebase_admin
from firebase_admin import credentials, auth
from loguru import logger

# Get the path from the environment variable we will set in the deployment
cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# Initialize Firebase only once
if not firebase_admin._apps:
    try:
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            logger.info("✅ Firebase initialized successfully from K8s Secret.")
        else:
            # Fallback for local development if you don't have the env var set
            logger.warning("⚠️ GOOGLE_APPLICATION_CREDENTIALS not found. Defaulting to local app.")
            firebase_admin.initialize_app()
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize Firebase: {e}")

firebase_auth = auth