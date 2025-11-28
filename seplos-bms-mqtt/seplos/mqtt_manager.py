"""
MQTT Manager with connection handling, reconnection, publish modes, and command subscriptions
"""

import time
import threading
import paho.mqtt.client as mqtt
from .logging_setup import get_logger


class MQTTManager:
    """
    MQTT Manager class - handles connection, reconnection, and publishing

    Features:
    - Automatic reconnection with exponential backoff
    - Publish-on-change mode to reduce traffic
    - Thread-safe publishing
    - Connection statistics
    - Command subscription for on-demand value requests
    """

    def __init__(self, server, port, username, password, prefix, publish_mode='changed'):
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.prefix = prefix
        self.publish_mode = publish_mode
        self.connected = False
        self.client = None
        self.last_values = {}
        self.lock = threading.Lock()
        self.log = get_logger()

        # Reconnection settings
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 0  # 0 = unlimited
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60

        # Stats
        self.messages_published = 0
        self.messages_skipped = 0
        self.last_publish_time = 0
        self.connection_count = 0
        self.disconnection_count = 0
        self.commands_received = 0

        # Command handler callback
        self._command_handler = None
        self._command_topic = f"R/{prefix}/#"

        self._setup_client()

    def _setup_client(self):
        """Setup MQTT client with callbacks"""
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if self.username:
            self.client.username_pw_set(username=self.username, password=self.password)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Enable automatic reconnection with configurable delays
        self.client.reconnect_delay_set(min_delay=self.reconnect_delay, max_delay=self.max_reconnect_delay)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Callback when connected to MQTT broker"""
        if reason_code == 0:
            self.connected = True
            self.connection_count += 1
            self.reconnect_attempts = 0
            self.log.info(f"MQTT connected to {self.server}:{self.port} (connection #{self.connection_count})")
            # Subscribe to command topic for on-demand requests
            self.client.subscribe(self._command_topic)
            self.log.info(f"Subscribed to command topic: {self._command_topic}")
        else:
            self.connected = False
            self.log.error(f"MQTT connection failed with code: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """Callback when disconnected from MQTT broker"""
        was_connected = self.connected
        self.connected = False
        self.disconnection_count += 1

        if was_connected:
            self.log.warning(f"MQTT disconnected (code: {reason_code}), attempting reconnect...")
        else:
            self.log.debug(f"MQTT disconnect callback (code: {reason_code})")

    def _on_message(self, client, userdata, message):
        """Callback when message received on subscribed topic"""
        try:
            topic = message.topic
            # Command topic format: R/seplos/battery_1/soc or R/seplos/pack/all
            # Extract the target topic by removing 'R/' prefix
            if topic.startswith("R/"):
                self.commands_received += 1
                target = topic[2:]  # Remove 'R/' prefix
                self.log.debug(f"Command received: {topic} -> republish {target}")

                if self._command_handler:
                    self._command_handler(target)
                else:
                    # Default: republish cached value if available
                    self._handle_republish_request(target)
        except Exception as e:
            self.log.error(f"Error processing command message: {e}")

    def _handle_republish_request(self, target):
        """Handle republish request for a specific topic"""
        with self.lock:
            # Target comes with prefix already (e.g., seplos/battery_1/soc)
            # Check for 'all' request first - republish all values for that entity
            if target.endswith('/all'):
                entity_prefix = target[:-4]  # Remove '/all' -> seplos/battery_1
                count = 0
                for cached_topic, value in self.last_values.items():
                    if cached_topic.startswith(entity_prefix):
                        self.publish(cached_topic, value, retain=True)
                        count += 1
                if count > 0:
                    self.log.debug(f"Republished {count} values for {entity_prefix}")
                else:
                    self.log.debug(f"No cached values found for {entity_prefix}")
                return

            # Check for exact match
            if target in self.last_values:
                value = self.last_values[target]
                self.publish(target, value, retain=True)
                self.log.debug(f"Republished: {target} = {value}")
            else:
                self.log.debug(f"Topic not in cache: {target}")

    def set_command_handler(self, handler):
        """Set custom command handler callback"""
        self._command_handler = handler

    def connect(self):
        """Connect to MQTT broker and start background loop"""
        try:
            self.log.info(f"Connecting to MQTT server {self.server}:{self.port}")
            self.client.connect(self.server, self.port, keepalive=60)
            # Start network loop in background thread (handles reconnection automatically)
            self.client.loop_start()
            # Wait a bit for connection to establish
            time.sleep(1)
            return self.connected
        except Exception as e:
            self.log.error(f"MQTT connection error: {e}")
            return False

    def disconnect(self):
        """Gracefully disconnect from MQTT broker"""
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception as e:
            self.log.debug(f"MQTT disconnect: {e}")
        finally:
            self.connected = False

    def publish(self, topic, value, retain=True):
        """Publish a message to MQTT (always publishes regardless of mode)"""
        if not self.connected:
            return False
        try:
            result = self.client.publish(topic, value, retain=retain)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.last_publish_time = time.time()
                return True
            else:
                self.log.warning(f"MQTT publish failed: {result.rc}")
                return False
        except Exception as e:
            self.log.error(f"MQTT publish error: {e}")
            return False

    def publish_if_changed(self, topic, value, retain=True):
        """Publish based on publish_mode setting"""
        if self.publish_mode == 'all':
            # Always publish
            self.messages_published += 1
            return self.publish(topic, value, retain)

        # Mode 'changed' - only publish if value changed
        with self.lock:
            if topic not in self.last_values or self.last_values[topic] != value:
                self.last_values[topic] = value
                self.messages_published += 1
                return self.publish(topic, value, retain)
            else:
                self.messages_skipped += 1
        return False

    def is_connected(self):
        """Check if connected to MQTT broker"""
        return self.connected

    def get_stats(self):
        """Return MQTT statistics"""
        return {
            'connected': self.connected,
            'messages_published': self.messages_published,
            'messages_skipped': self.messages_skipped,
            'publish_mode': self.publish_mode,
            'connection_count': self.connection_count,
            'disconnection_count': self.disconnection_count,
            'last_publish_time': self.last_publish_time,
            'commands_received': self.commands_received
        }

    def clear_cached_values(self):
        """Clear cached values (useful for forcing republish after reconnect)"""
        with self.lock:
            self.last_values.clear()
        self.log.debug("MQTT cached values cleared")
