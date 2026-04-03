# Use the lightweight slim version
FROM python:3.12-slim

# 1. Set environment variables for optimized Python execution
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 2. Create a secure, non-root user for Kubernetes
RUN addgroup --system appgroup && adduser --system --group appuser

# 3. Install necessary system dependencies (libpq-dev is crucial for psycopg/Postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. Upgrade core Python packaging tools
RUN python -m ensurepip --upgrade && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

# 5. Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of your application code
COPY . .

# 7. Secure the files by handing ownership to the non-root user
RUN chown -R appuser:appgroup /app

# 8. Switch to the non-root user to run the application
USER appuser

# Expose the container port
EXPOSE 8000

# 9. 🚀 CRITICAL: Run Gunicorn for production!
# IMPORTANT: Change "your_project_name" to the actual name of your inner Django folder!
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "order_service.wsgi:application"]