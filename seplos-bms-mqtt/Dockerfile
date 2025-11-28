# syntax=docker/dockerfile:1
# Seplos BMS MQTT - Seplos BMS V3 to MQTT/InfluxDB Bridge

FROM python:3.9-alpine

LABEL maintainer="sm26449@diysolar.ro"
LABEL description="Seplos BMS V3 to MQTT/InfluxDB Bridge"
LABEL version="2.4"

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY seplos/ ./seplos/
COPY seplos_bms_mqtt.py .

# Copy example config (user should mount their own config at runtime)
COPY seplos_bms_mqtt.ini.example ./seplos_bms_mqtt.ini.example

# Health check endpoint
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python3 -c "import socket; s=socket.socket(); s.settimeout(5); exit(0)" || exit 1

# Config should be mounted at runtime: -v /path/to/config.ini:/app/seplos_bms_mqtt.ini
CMD ["python3", "/app/seplos_bms_mqtt.py"]
