# Multi-stage build for Anki Sync Server
FROM python:3.10-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Development stage
FROM base as development
COPY requirements.txt .
RUN pip install -r requirements.txt
# Install dev dependencies
RUN pip install pytest webtest mkdocs jupyter jupyterlab black mkdocs-jupyter
COPY . .
WORKDIR /app/src
RUN pip install -e .
WORKDIR /app
CMD ["python", "-m", "ankisyncd"]

# Production stage
FROM base as production
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy source code
COPY src /app/src
WORKDIR /app/src
RUN pip install -e .

# Copy configuration files
COPY src/ankisyncd     /app/ankisyncd
COPY src/ankisyncd_cli /app/ankisyncd_cli
COPY src/ankisyncd.conf /app/ankisyncd.conf

# Configure paths for Docker environment
RUN sed -i -e '/data_root =/       s/= .*/= \/data\/collections/' /app/ankisyncd.conf \
 && sed -i -e '/auth_db_path =/    s/= .*/= \/data\/auth\.db/'    /app/ankisyncd.conf \
 && sed -i -e '/session_db_path =/ s/= .*/= \/data\/session.db/'  /app/ankisyncd.conf

# Create data directory
RUN mkdir -p /data/collections

# Set working directory
WORKDIR /app

# Expose port
EXPOSE 27701

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:27701/status')" || exit 1

# Default command
CMD ["python", "-m", "ankisyncd"]
