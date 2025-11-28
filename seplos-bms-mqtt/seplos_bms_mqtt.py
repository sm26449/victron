#!/usr/bin/env python3
"""
Seplos BMS MQTT v2.4 - Seplos BMS V3 to MQTT/InfluxDB Bridge

An enhanced fork of Seplos3MQTT (https://github.com/Russel-Roberts/Seplos3MQTT)
with modular architecture and additional features.

Features:
- MQTT autodiscovery for Home Assistant
- Pack aggregate calculations for battery banks
- Optional InfluxDB integration
- Health monitoring with stale data detection
- MQTT command subscription for on-demand value requests
- Smart publish modes (changed/all)
- File logging support
- MQTT and InfluxDB reconnection logic
"""

import sys
import threading

from seplos import (
    setup_logging,
    get_logger,
    get_config,
    MQTTManager,
    InfluxDBManager,
    PackAggregator,
    SerialSnooper,
    HealthMonitor,
    __version__,
)
from seplos.config import print_help


def main():
    """Main entry point"""
    print(" ")
    print(f"Seplos BMS MQTT v{__version__} - Seplos BMS V3 to MQTT/InfluxDB")
    print("-" * 50)

    influxdb_manager = None
    health_monitor = None

    try:
        # Load configuration
        # General settings
        log_level = get_config('general', 'log_level', 'INFO').upper()
        log_file = get_config('general', 'log_file', '')

        # Setup logging (with optional file logging)
        log = setup_logging(
            log_level=log_level,
            log_file=log_file if log_file else None
        )
        log.info(f"Log level set to: {log_level}")

        # Serial settings
        port = get_config('serial', 'port')
        baudrate = int(get_config('serial', 'baudrate', '19200'))

        # MQTT settings
        mqtt_server = get_config('mqtt', 'server')
        mqtt_port = int(get_config('mqtt', 'port', '1883'))
        mqtt_user = get_config('mqtt', 'username', '')
        mqtt_pass = get_config('mqtt', 'password', '')
        mqtt_prefix = get_config('mqtt', 'prefix', 'seplos')
        mqtt_publish_mode = get_config('mqtt', 'publish_mode', 'changed')

        # Health check settings
        health_check_interval = int(get_config('health', 'check_interval', '60'))
        stale_timeout = int(get_config('health', 'stale_timeout', '120'))

        # InfluxDB settings (optional)
        influxdb_enabled = get_config('influxdb', 'enabled', 'false').lower() == 'true'
        influxdb_url = get_config('influxdb', 'url', '')
        influxdb_token = get_config('influxdb', 'token', '')
        influxdb_org = get_config('influxdb', 'org', '')
        influxdb_bucket = get_config('influxdb', 'bucket', 'seplos')
        influxdb_write_interval = int(get_config('influxdb', 'write_interval', '5'))
        influxdb_publish_mode = get_config('influxdb', 'publish_mode', 'changed')

        # Initialize MQTT Manager
        mqtt_manager = MQTTManager(
            mqtt_server, mqtt_port, mqtt_user, mqtt_pass,
            mqtt_prefix, mqtt_publish_mode
        )
        if not mqtt_manager.connect():
            log.error("Failed to connect to MQTT broker. Exiting.")
            sys.exit(1)
        log.info(f"MQTT connected (publish_mode: {mqtt_publish_mode})")

        # Initialize InfluxDB Manager (optional)
        if influxdb_enabled and influxdb_url and influxdb_token:
            influxdb_manager = InfluxDBManager(
                influxdb_url, influxdb_token, influxdb_org, influxdb_bucket,
                enabled=True,
                write_interval=influxdb_write_interval,
                publish_mode=influxdb_publish_mode
            )
            if influxdb_manager.is_enabled():
                log.info(f"InfluxDB Manager initialized (mode: {influxdb_publish_mode}, interval: {influxdb_write_interval}s)")
            else:
                log.warning("InfluxDB configured but failed to connect")
        else:
            log.info("InfluxDB disabled (not configured)")

        # Initialize Pack Aggregator
        pack_aggregator = PackAggregator(mqtt_manager, mqtt_prefix, influxdb_manager)
        log.info("Pack Aggregator initialized")

        # Initialize and start Health Monitor
        health_monitor = HealthMonitor(
            mqtt_manager, mqtt_prefix, influxdb_manager, pack_aggregator,
            check_interval=health_check_interval,
            stale_timeout=stale_timeout
        )
        health_monitor.start()

        # Initialize and run sniffer
        with SerialSnooper(port, mqtt_manager, mqtt_prefix, pack_aggregator, baudrate) as sniffer:
            # Update health monitor with declared batteries reference
            health_monitor.set_declared_batteries(sniffer.batts_declared_set)

            log.info(f"Sniffer started on {port} @ {baudrate}. Listening for Seplos BMS data...")

            while True:
                data = sniffer.read_raw()
                sniffer.process_data(data)

    except KeyboardInterrupt:
        log.info("Shutdown requested...")
    except Exception as e:
        log = get_logger()
        log.error(f'Unexpected error: {e}')
        print_help()
    finally:
        if health_monitor:
            health_monitor.stop()
        if influxdb_manager:
            influxdb_manager.close()
        if 'mqtt_manager' in locals():
            mqtt_manager.disconnect()


if __name__ == "__main__":
    main()
