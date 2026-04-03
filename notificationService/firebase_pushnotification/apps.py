from django.apps import AppConfig
import logging
import os
from django.conf import settings

logger = logging.getLogger(__name__)

class FirebasePushnotificationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "firebase_pushnotification"

    def ready(self):
        self._init_firebase()

    def _init_firebase(self):
        try:
            import firebase_admin
            from firebase_admin import credentials
            
            # (Keep your other imports here if you need them)
            # from .services import fcm_service
            # from email_service import task

            if not firebase_admin._apps:
                # 🚀 UPGRADED: Check for the Kubernetes environment variable first
                cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

                if cred_path and os.path.exists(cred_path):
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                    logger.info("🔥 Firebase Admin initialized successfully from K8s Secret.")
                else:
                    # Fallback for local development on your Mac
                    logger.warning("⚠️ GOOGLE_APPLICATION_CREDENTIALS not found. Falling back to local file.")
                    fallback_path = os.path.join(
                        settings.BASE_DIR,
                        "firebase/firebase-credentials.json"
                    )
                    
                    if os.path.exists(fallback_path):
                        cred = credentials.Certificate(fallback_path)
                        firebase_admin.initialize_app(cred)
                        logger.info("🔥 Firebase Admin initialized from local fallback path.")
                    else:
                        # Absolute last resort (relies on default environment auth)
                        firebase_admin.initialize_app()
                        logger.warning("🔥 Firebase Admin initialized with default credentials.")
                        
            else:
                logger.info("ℹ️ Firebase already initialized")

        except Exception as e:
            logger.error(f"❌ Firebase init failed: {e}")