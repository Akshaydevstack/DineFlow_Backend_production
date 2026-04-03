# Use the slim version to save space
FROM python:3.12-slim

# 1. Set environment variables for optimized Python execution
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 2. Create a non-root user for Kubernetes security
RUN addgroup --system appgroup && adduser --system --group appuser

# 3. Install system dependencies (added libpq-dev for Postgres stability)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. Upgrade core packaging tools
RUN python -m ensurepip --upgrade && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

# 5. Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy the rest of your application code
COPY . .

# 7. Change ownership of the files to our secure user
RUN chown -R appuser:appgroup /app

# 8. Switch to the non-root user before running the app
USER appuser

# Expose the port
EXPOSE 8000

# 9. 🚀 CRITICAL: Run Gunicorn instead of runserver for production!
# Note: "auth_service.wsgi:application" assumes your inner Django project folder is named "auth_service".
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "auth_service.wsgi:application"]