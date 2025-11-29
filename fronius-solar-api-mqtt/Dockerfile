FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY pyfronius/ ./pyfronius/
COPY fronius_collector/ ./fronius_collector/

# Create config directory
RUN mkdir -p /config

# Set environment variable for config path
ENV FRONIUS_CONFIG=/config/config.yaml

# Run the collector
CMD ["python", "-m", "fronius_collector"]
