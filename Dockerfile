# Python environment for USCIS Knowledge Base scripts
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY scripts/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy scripts
COPY scripts/ ./scripts/
COPY .env* ./

ENV PYTHONUNBUFFERED=1
