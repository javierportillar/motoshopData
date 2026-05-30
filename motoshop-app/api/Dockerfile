FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dep resolution
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml .
COPY src/ src/
COPY users.yaml .

# Install dependencies (uv reads pyproject.toml)
RUN uv pip install --system --no-cache .

# Override path resolution: __file__ points to site-packages after pip install
ENV USERS_FILE_PATH=/app/users.yaml

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000

CMD ["uvicorn", "motoshop_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
