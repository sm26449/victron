"""YAML Configuration loader for Fronius Modbus MQTT"""

import os
import yaml
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ModbusConfig:
    """Modbus TCP connection settings"""
    host: str
    port: int = 502
    timeout: int = 3
    retry_attempts: int = 2
    retry_delay: float = 0.1


@dataclass
class DevicesConfig:
    """Device configuration - explicit device IDs"""
    inverters: List[int] = field(default_factory=list)  # List of inverter Modbus IDs
    meters: List[int] = field(default_factory=list)      # List of meter Modbus IDs
    meter_poll_interval: float = 2.0    # Meter polling interval in seconds
    inverter_poll_delay: float = 1.0    # Delay between inverter reads in seconds
    inverter_read_delay_ms: int = 200   # Delay between register blocks within same inverter


@dataclass
class MQTTConfig:
    """MQTT broker settings"""
    enabled: bool = True
    broker: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    topic_prefix: str = "fronius"
    retain: bool = True
    qos: int = 0


@dataclass
class InfluxDBConfig:
    """InfluxDB settings"""
    enabled: bool = False
    url: str = ""
    token: str = ""
    org: str = ""
    bucket: str = "fronius"
    write_interval: int = 5
    publish_mode: str = ""  # Empty = use general.publish_mode


@dataclass
class GeneralConfig:
    """General application settings"""
    log_level: str = "INFO"
    log_file: str = ""
    poll_interval: int = 5
    publish_mode: str = "changed"  # 'changed' or 'all'


class ConfigLoader:
    """YAML configuration loader with singleton pattern"""

    _instance: Optional['ConfigLoader'] = None

    def __init__(self, config_path: str = None):
        self.config: Dict = {}
        self.general: GeneralConfig = None
        self.modbus: ModbusConfig = None
        self.devices: DevicesConfig = None
        self.mqtt: MQTTConfig = None
        self.influxdb: InfluxDBConfig = None
        self._load_config(config_path)

    @classmethod
    def get_instance(cls, config_path: str = None) -> 'ConfigLoader':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = ConfigLoader(config_path)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton (useful for testing)"""
        cls._instance = None

    def _load_config(self, config_path: str = None):
        """Load and parse YAML configuration"""
        paths = [
            config_path,
            os.environ.get('FRONIUS_CONFIG'),
            '/app/config/fronius_modbus_mqtt.yaml',
            'config/fronius_modbus_mqtt.yaml',
            'fronius_modbus_mqtt.yaml'
        ]

        for path in filter(None, paths):
            if os.path.exists(path):
                with open(path, 'r') as f:
                    self.config = yaml.safe_load(f)
                self._parse_config()
                return

        raise FileNotFoundError(
            "No configuration file found. Searched paths:\n" +
            "\n".join(f"  - {p}" for p in filter(None, paths))
        )

    def _parse_config(self):
        """Parse configuration into dataclasses"""
        # Parse general settings
        gen = self.config.get('general', {})
        self.general = GeneralConfig(
            log_level=gen.get('log_level', 'INFO'),
            log_file=gen.get('log_file', ''),
            poll_interval=gen.get('poll_interval', 5),
            publish_mode=gen.get('publish_mode', 'changed')
        )

        # Parse modbus settings (required)
        mb = self.config.get('modbus', {})
        if not mb.get('host'):
            raise ValueError("modbus.host is required in configuration")

        self.modbus = ModbusConfig(
            host=mb.get('host'),
            port=mb.get('port', 502),
            timeout=mb.get('timeout', 3),
            retry_attempts=mb.get('retry_attempts', 2),
            retry_delay=mb.get('retry_delay', 0.1)
        )

        # Parse devices settings
        dev = self.config.get('devices', {})
        inverters = dev.get('inverters', [1])
        meters = dev.get('meters', [240])
        # Handle single int or list
        if isinstance(inverters, int):
            inverters = [inverters]
        if isinstance(meters, int):
            meters = [meters]

        self.devices = DevicesConfig(
            inverters=inverters,
            meters=meters,
            meter_poll_interval=dev.get('meter_poll_interval', 2.0),
            inverter_poll_delay=dev.get('inverter_poll_delay', 1.0),
            inverter_read_delay_ms=dev.get('inverter_read_delay_ms', 200)
        )

        # Parse MQTT settings
        mq = self.config.get('mqtt', {})
        self.mqtt = MQTTConfig(
            enabled=mq.get('enabled', True),
            broker=mq.get('broker', 'localhost'),
            port=mq.get('port', 1883),
            username=mq.get('username', ''),
            password=mq.get('password', ''),
            topic_prefix=mq.get('topic_prefix', 'fronius'),
            retain=mq.get('retain', True),
            qos=mq.get('qos', 0)
        )

        # Parse InfluxDB settings
        idb = self.config.get('influxdb', {})
        self.influxdb = InfluxDBConfig(
            enabled=idb.get('enabled', False),
            url=idb.get('url', ''),
            token=idb.get('token', ''),
            org=idb.get('org', ''),
            bucket=idb.get('bucket', 'fronius'),
            write_interval=idb.get('write_interval', 5),
            publish_mode=idb.get('publish_mode', '')
        )


def get_config(config_path: str = None) -> ConfigLoader:
    """Get configuration singleton"""
    return ConfigLoader.get_instance(config_path)
