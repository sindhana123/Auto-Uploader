# Stage 1: Build the requirements
FROM python:3.11-slim-bookworm AS builder

# Prevent writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies (required for tgcrypto or motor if binary wheels are missing)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install python packages in the user site-packages directory
RUN pip install --user --no-cache-dir -r requirements.txt


# Stage 2: Final lightweight image
FROM python:3.11-slim-bookworm

# Environment optimizations
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install ffmpeg which is required for our bot video muxing and metadata extraction
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy installed python packages from builder stage to reduce size
COPY --from=builder /root/.local /root/.local

# Ensure the local bin is in PATH
ENV PATH=/root/.local/bin:$PATH

# Copy our bot application code
COPY . .

# Run the bot main module
CMD ["python3", "main.py"]
