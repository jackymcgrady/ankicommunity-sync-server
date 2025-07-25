# Multi-stage build for Anki Sync Server - Optimized
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install minimal build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get autoremove -y \
    && apt-get autoclean

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create app directory
WORKDIR /app

# Install Python dependencies in builder
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy and install source code
COPY src /app/src
WORKDIR /app/src
RUN pip install --no-cache-dir -e .

# Production stage
FROM python:3.11-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
    PATH="/opt/venv/bin:$PATH"

# Install only essential runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get autoremove -y \
    && apt-get autoclean

# Create non-root user
RUN groupadd -g 1000 anki && useradd -u 1000 -g anki -m anki

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application files
COPY --from=builder /app/src/ankisyncd /app/ankisyncd
COPY --from=builder /app/src/ankisyncd_cli /app/ankisyncd_cli
COPY --from=builder /app/src/ankisyncd.conf /app/ankisyncd.conf

# Configure paths for Docker environment
RUN sed -i -e '/data_root =/       s/= .*/= \/data\/collections/' /app/ankisyncd.conf \
 && sed -i -e '/auth_db_path =/    s/= .*/= \/data\/auth\.db/'    /app/ankisyncd.conf \
 && sed -i -e '/session_db_path =/ s/= .*/= \/data\/session.db/'  /app/ankisyncd.conf

# Create data directory with proper permissions
RUN mkdir -p /data/collections && chown -R anki:anki /data /app

# Set working directory
WORKDIR /app

# Switch to non-root user
USER anki

# Expose port
EXPOSE 27702

# Health check using basic Python instead of requests
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:27702/').read()" || exit 1

# Default command
CMD ["python", "-m", "ankisyncd"]
