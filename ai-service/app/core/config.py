import os

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT == "production"

# Microservices URLs
CART_SERVICE_URL = os.getenv("CART_SERVICE_URL", "http://cart-service.dineflow-production.svc.cluster.local:8000")
MENU_SERVICE_URL = os.getenv("MENU_SERVICE_URL", "http://menu-service.dineflow-production.svc.cluster.local:8000")
ORDERS_SERVICE_URL = os.getenv("ORDERS_SERVICE_URL", "http://order-service.dineflow-production.svc.cluster.local:8000")

# Database configurations
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis-service")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# AWS DynamoDB config
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

# LLM configurations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Email credentials
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
