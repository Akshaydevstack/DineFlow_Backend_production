# 1. Use the slim version to save ~600MB right off the bat!
FROM python:3.12-slim-bookworm

# 2. Set environment variables for optimized Python execution
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# 3. Create a non-root user for Kubernetes security
RUN addgroup --system appgroup && adduser --system --group appuser

# 4. Install standard system dependencies required for pgvector/psycopg and clean up cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Layer 1 & 2 — Install pip tools and CPU-only PyTorch
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 6. Layer 3 — Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 7. Layer 4 — Pre-download the model into the image
RUN python -c "from sentence_transformers import SentenceTransformer; \
    model = SentenceTransformer('all-MiniLM-L6-v2'); \
    model.save('/app/models/all-MiniLM-L6-v2')"

# 8. Layer 5 — Copy application code
COPY app/ ./app/

# 9. Change ownership of the files to our secure user
RUN chown -R appuser:appgroup /app

# 10. Switch to the non-root user before running the app
USER appuser

EXPOSE 8001

# Run Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]