"""
Health Monitor - health checks, watchdog, and stale data detection
"""

import time
import threading
from .logging_setup import get_logger


class HealthMonitor:
    """
    Health Monitor class - monitors system health and battery data freshness

    Features:
    - Periodic health status publishing
    - Stale data detection and battery offline marking
    - System statistics reporting
    - Watchdog functionality
    """

    def __init__(self, mqtt_manager, mqtt_prefix, influxdb_manager=None, pack_aggregator=None,
                 check_interval=60, stale_timeout=120):
        self.mqtt = mqtt_manager
        self.mqtt_prefix = mqtt_prefix
        self.influxdb = influxdb_manager
        self.pack_aggregator = pack_aggregator
        self.check_interval = check_interval
        self.stale_timeout = stale_timeout
        self.log = get_logger()

        self.start_time = time.time()
        self.stop_event = threading.Event()
        self.thread = None
        self.declared_batteries = set()

        # Statistics
        self.health_checks_performed = 0
        self.stale_batteries_detected = 0
        self.last_health_check = 0

    def set_declared_batteries(self, batteries_set):
        """Update the set of declared batteries"""
        self.declared_batteries = batteries_set

    def start(self):
        """Start the health monitor thread"""
        if self.check_interval <= 0:
            self.log.info("Health monitor disabled (interval=0)")
            return

        self.thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True,
            name="HealthMonitor"
        )
        self.thread.start()
        self.log.info(f"Health monitor started (interval: {self.check_interval}s, stale timeout: {self.stale_timeout}s)")

    def stop(self):
        """Stop the health monitor thread"""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def _health_check_loop(self):
        """Background thread to publish health status periodically"""
        while not self.stop_event.is_set():
            self.stop_event.wait(self.check_interval)
            if self.stop_event.is_set():
                break

            self._perform_health_check()

    def _perform_health_check(self):
        """Perform a health check and publish status"""
        self.health_checks_performed += 1
        self.last_health_check = time.time()
        uptime = int(time.time() - self.start_time)

        # Build health data
        health_data = {
            'uptime_seconds': uptime,
            'mqtt_connected': self.mqtt.is_connected(),
            'timestamp': int(time.time()),
            'health_checks_performed': self.health_checks_performed
        }

        # Add InfluxDB stats if enabled
        if self.influxdb:
            stats = self.influxdb.get_stats()
            health_data['influxdb_connected'] = stats['connected']
            health_data['influxdb_writes_total'] = stats['writes_total']
            health_data['influxdb_writes_failed'] = stats['writes_failed']
            health_data['influxdb_publish_mode'] = stats['publish_mode']
            health_data['influxdb_reconnect_count'] = stats.get('reconnect_count', 0)

        # Publish health data
        self.mqtt.publish(f"{self.mqtt_prefix}/health/uptime", uptime, retain=True)
        self.mqtt.publish(f"{self.mqtt_prefix}/health/mqtt_connected",
                        "true" if health_data['mqtt_connected'] else "false", retain=True)
        self.mqtt.publish(f"{self.mqtt_prefix}/health/health_checks", self.health_checks_performed, retain=True)

        if self.influxdb:
            self.mqtt.publish(f"{self.mqtt_prefix}/health/influxdb_connected",
                            "true" if health_data['influxdb_connected'] else "false", retain=True)
            self.mqtt.publish(f"{self.mqtt_prefix}/health/influxdb_writes_total",
                            health_data['influxdb_writes_total'], retain=True)
            self.mqtt.publish(f"{self.mqtt_prefix}/health/influxdb_writes_failed",
                            health_data['influxdb_writes_failed'], retain=True)

        # Publish MQTT stats
        mqtt_stats = self.mqtt.get_stats()
        self.mqtt.publish(f"{self.mqtt_prefix}/health/mqtt_messages_published",
                        mqtt_stats['messages_published'], retain=True)
        self.mqtt.publish(f"{self.mqtt_prefix}/health/mqtt_messages_skipped",
                        mqtt_stats['messages_skipped'], retain=True)
        self.mqtt.publish(f"{self.mqtt_prefix}/health/mqtt_publish_mode",
                        mqtt_stats['publish_mode'], retain=True)
        self.mqtt.publish(f"{self.mqtt_prefix}/health/mqtt_connection_count",
                        mqtt_stats.get('connection_count', 1), retain=True)
        self.mqtt.publish(f"{self.mqtt_prefix}/health/mqtt_disconnection_count",
                        mqtt_stats.get('disconnection_count', 0), retain=True)
        self.mqtt.publish(f"{self.mqtt_prefix}/health/mqtt_commands_received",
                        mqtt_stats.get('commands_received', 0), retain=True)

        # Check for stale batteries and mark offline
        self._check_stale_batteries()

        self.log.debug(f"Health check: uptime={uptime}s, mqtt={health_data['mqtt_connected']}")

    def _check_stale_batteries(self):
        """Check for stale battery data and mark batteries as offline"""
        if not self.pack_aggregator:
            return

        current_time = time.time()
        all_batteries = self.pack_aggregator.get_all_batteries()
        stale_count = 0

        for batt_id, batt_data in all_batteries.items():
            last_update = batt_data.get('last_update', 0)
            time_since_update = current_time - last_update

            if time_since_update > self.stale_timeout:
                stale_count += 1
                # Mark battery as offline if it was previously declared
                if batt_id in self.declared_batteries:
                    self.log.warning(f"Battery {batt_id} data stale ({int(time_since_update)}s), marking offline")
                    self.mqtt.publish(f"{self.mqtt_prefix}/battery_{batt_id}/state", "offline", retain=True)
                    self.stale_batteries_detected += 1

        # Publish stale battery count
        if stale_count > 0:
            self.mqtt.publish(f"{self.mqtt_prefix}/health/stale_batteries", stale_count, retain=True)
        else:
            self.mqtt.publish(f"{self.mqtt_prefix}/health/stale_batteries", 0, retain=True)

        # Publish online/total battery counts
        online_batteries = self.pack_aggregator.get_online_batteries(timeout=self.stale_timeout)
        self.mqtt.publish(f"{self.mqtt_prefix}/health/batteries_online", len(online_batteries), retain=True)
        self.mqtt.publish(f"{self.mqtt_prefix}/health/batteries_total", len(all_batteries), retain=True)

    def get_stats(self):
        """Return health monitor statistics"""
        return {
            'uptime_seconds': int(time.time() - self.start_time),
            'health_checks_performed': self.health_checks_performed,
            'stale_batteries_detected': self.stale_batteries_detected,
            'last_health_check': self.last_health_check,
            'check_interval': self.check_interval,
            'stale_timeout': self.stale_timeout
        }

    def is_healthy(self):
        """Check if the system is healthy"""
        # System is healthy if MQTT is connected and we've had recent data
        mqtt_ok = self.mqtt.is_connected()

        # Check if we have any online batteries
        batteries_ok = True
        if self.pack_aggregator:
            online = self.pack_aggregator.get_online_batteries(timeout=self.stale_timeout)
            batteries_ok = len(online) > 0

        return mqtt_ok and batteries_ok
