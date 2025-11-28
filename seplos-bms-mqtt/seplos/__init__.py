"""
Seplos BMS MQTT - Seplos BMS V3 to MQTT/InfluxDB Bridge

An enhanced fork of Seplos3MQTT with modular architecture and additional features.
https://github.com/sm2669/seplos-bms-mqtt
"""

from .config import ConfigLoader, get_config
from .mqtt_manager import MQTTManager
from .influxdb_manager import InfluxDBManager
from .pack_aggregator import PackAggregator
from .serial_snooper import SerialSnooper
from .health_monitor import HealthMonitor
from .utils import calc_crc16, to_lower_under
from .logging_setup import setup_logging, get_logger

__version__ = "2.4"
__all__ = [
    '__version__',
    'ConfigLoader',
    'get_config',
    'MQTTManager',
    'InfluxDBManager',
    'PackAggregator',
    'SerialSnooper',
    'HealthMonitor',
    'calc_crc16',
    'to_lower_under',
    'setup_logging',
    'get_logger',
]
