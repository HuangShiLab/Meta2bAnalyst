FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/

# NOTE: R integration (DESeq2 / edgeR / vegan / phyloseq / ANCOMBC / ALDEx2 /
# MaAsLin3 / mixOmics / WGCNA) is NOT installed in this image. Those methods
# refuse to run rather than silently substituting a Python approximation, so the
# image is honest about what it can compute. To enable them, extend this stage:
#
#   RUN apt-get update && apt-get install -y --no-install-recommends \
#         r-base r-base-dev libcurl4-openssl-dev libssl-dev libxml2-dev \
#       && rm -rf /var/lib/apt/lists/*
#   RUN pip install --no-cache-dir rpy2==3.5.15
#   RUN python scripts/install_r_packages.py
#
# This adds roughly 1.5 GB and a long build; keep it in a separate image tag if
# most users only need the Python analyses.

# Create uploads and logs directories
RUN mkdir -p uploads logs

# Set environment variables
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
