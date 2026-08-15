FROM python:3.11-slim

# Install system dependencies (ffmpeg, rclone, ca-certificates, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    rclone \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and files
COPY . .

# Ensure downloads directory exists
RUN mkdir -p downloads_temp

CMD ["python", "src/main.py"]
