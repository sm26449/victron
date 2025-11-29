"""Configuration loader for Fronius Collector."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class FroniusConfig:
    """Fronius DataManager configuration."""

    host: str
    inverter_ids: list[int] = field(default_factory=lambda: [1])
    meter_id: int = 0
    poll_interval: int = 10
    # Fast polling for power_flow and meter (can be 1 second)
    poll_interval_fast: int = 0  # 0 = disabled, use poll_interval for all
    # Slow polling for inverter info (status, error codes) - less frequent
    poll_interval_inverter_info: int = 60  # inverter_info changes rarely
    timeout: int = 10


@dataclass
class MQTTConfig:
    """MQTT broker configuration."""

    enabled: bool = True
    host: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    base_topic: str = "fronius"
    retain: bool = True
    qos: int = 1
    publish_mode: str = "on_change"  # "always" or "on_change"
    client_id: str = ""
    reconnect_delay: int = 5


@dataclass
class InfluxDBConfig:
    """InfluxDB v2 configuration."""

    enabled: bool = True
    url: str = "http://localhost:8086"
    token: str = ""
    org: str = ""
    bucket: str = "fronius"
    write_mode: str = "on_change"  # "always" or "on_change"
    batch_size: int = 100
    flush_interval: int = 10


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    file: str = ""


@dataclass
class Config:
    """Main configuration container."""

    fronius: FroniusConfig
    mqtt: MQTTConfig
    influxdb: InfluxDBConfig
    logging: LoggingConfig


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file. If None, looks for config.yaml
                     in current directory or uses CONFIG_PATH env var.

    Returns:
        Config object with all settings.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If config file is invalid.
    """
    if config_path is None:
        config_path = os.environ.get("FRONIUS_CONFIG", "config.yaml")

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError("Config file is empty")

    # Parse fronius section
    fronius_data = data.get("fronius", {})
    if not fronius_data.get("host"):
        raise ValueError("fronius.host is required")

    fronius = FroniusConfig(
        host=fronius_data["host"],
        inverter_ids=fronius_data.get("inverter_ids", [1]),
        meter_id=fronius_data.get("meter_id", 0),
        poll_interval=fronius_data.get("poll_interval", 10),
        poll_interval_fast=fronius_data.get("poll_interval_fast", 0),
        poll_interval_inverter_info=fronius_data.get("poll_interval_inverter_info", 60),
        timeout=fronius_data.get("timeout", 10),
    )

    # Parse mqtt section
    mqtt_data = data.get("mqtt", {})
    mqtt = MQTTConfig(
        enabled=mqtt_data.get("enabled", True),
        host=mqtt_data.get("host", "localhost"),
        port=mqtt_data.get("port", 1883),
        username=mqtt_data.get("username", ""),
        password=mqtt_data.get("password", ""),
        base_topic=mqtt_data.get("base_topic", "fronius"),
        retain=mqtt_data.get("retain", True),
        qos=mqtt_data.get("qos", 1),
        publish_mode=mqtt_data.get("publish_mode", "on_change"),
        client_id=mqtt_data.get("client_id", ""),
        reconnect_delay=mqtt_data.get("reconnect_delay", 5),
    )

    # Parse influxdb section
    influx_data = data.get("influxdb", {})
    influxdb = InfluxDBConfig(
        enabled=influx_data.get("enabled", True),
        url=influx_data.get("url", "http://localhost:8086"),
        token=influx_data.get("token", ""),
        org=influx_data.get("org", ""),
        bucket=influx_data.get("bucket", "fronius"),
        write_mode=influx_data.get("write_mode", "on_change"),
        batch_size=influx_data.get("batch_size", 100),
        flush_interval=influx_data.get("flush_interval", 10),
    )

    # Parse logging section
    log_data = data.get("logging", {})
    logging_config = LoggingConfig(
        level=log_data.get("level", "INFO"),
        file=log_data.get("file", ""),
    )

    return Config(
        fronius=fronius,
        mqtt=mqtt,
        influxdb=influxdb,
        logging=logging_config,
    )


def setup_logging(config: LoggingConfig) -> None:
    """Configure logging based on config."""
    level = getattr(logging, config.level.upper(), logging.INFO)

    handlers: list[logging.Handler] = []

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    handlers.append(console_handler)

    # File handler (if configured)
    if config.file:
        file_handler = logging.FileHandler(config.file)
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(level=level, handlers=handlers, force=True)
