"""Resilient MQTT client for Fronius Collector."""

import asyncio
import json
import logging
import uuid
from typing import Any, Optional

import aiomqtt

from .config import MQTTConfig

logger = logging.getLogger(__name__)


class MQTTClient:
    """Async MQTT client with automatic reconnection and change detection."""

    def __init__(self, config: MQTTConfig):
        """Initialize MQTT client.

        Args:
            config: MQTT configuration.
        """
        self.config = config
        self._client: Optional[aiomqtt.Client] = None
        self._connected = False
        self._last_values: dict[str, Any] = {}
        self._reconnect_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()

        # Generate client ID if not provided
        self._client_id = config.client_id or f"fronius-collector-{uuid.uuid4().hex[:8]}"

    @property
    def connected(self) -> bool:
        """Return True if connected to broker."""
        return self._connected

    async def start(self) -> None:
        """Start the MQTT client and connect to broker."""
        if not self.config.enabled:
            logger.info("MQTT is disabled in config")
            return

        self._running = True
        await self._connect()

    async def stop(self) -> None:
        """Stop the MQTT client and disconnect."""
        self._running = False

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        await self._disconnect()
        logger.info("MQTT client stopped")

    async def _connect(self) -> None:
        """Connect to MQTT broker."""
        if not self._running:
            return

        try:
            self._client = aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username or None,
                password=self.config.password or None,
                identifier=self._client_id,
            )
            await self._client.__aenter__()
            self._connected = True
            logger.info(f"Connected to MQTT broker at {self.config.host}:{self.config.port}")

        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            self._connected = False
            self._schedule_reconnect()

    async def _disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error during MQTT disconnect: {e}")
            finally:
                self._client = None
                self._connected = False

    def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt."""
        if not self._running:
            return

        if self._reconnect_task and not self._reconnect_task.done():
            return

        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Attempt to reconnect to the broker."""
        while self._running and not self._connected:
            logger.info(
                f"Attempting MQTT reconnection in {self.config.reconnect_delay}s..."
            )
            await asyncio.sleep(self.config.reconnect_delay)

            if not self._running:
                break

            await self._disconnect()
            await self._connect()

    async def publish(
        self,
        topic: str,
        payload: Any,
        force: bool = False,
    ) -> bool:
        """Publish a message to MQTT.

        Args:
            topic: Topic suffix (will be prefixed with base_topic).
            payload: Data to publish (will be JSON encoded if dict/list).
            force: Force publish even if value hasn't changed.

        Returns:
            True if published successfully, False otherwise.
        """
        if not self.config.enabled:
            return False

        if not self._connected or not self._client:
            logger.warning(f"Cannot publish to {topic}: not connected")
            self._schedule_reconnect()
            return False

        full_topic = f"{self.config.base_topic}/{topic}"

        # Check for changes if in on_change mode
        if self.config.publish_mode == "on_change" and not force:
            if self._has_value_changed(full_topic, payload) is False:
                logger.debug(f"Skipping {full_topic}: value unchanged")
                return True

        # Encode payload
        if isinstance(payload, (dict, list)):
            message = json.dumps(payload)
        elif payload is None:
            message = ""
        else:
            message = str(payload)

        try:
            async with self._lock:
                await self._client.publish(
                    full_topic,
                    message,
                    qos=self.config.qos,
                    retain=self.config.retain,
                )

            # Update last value cache
            self._last_values[full_topic] = payload
            logger.debug(f"Published to {full_topic}: {message[:100]}")
            return True

        except aiomqtt.MqttError as e:
            logger.error(f"MQTT publish error: {e}")
            self._connected = False
            self._schedule_reconnect()
            return False

        except Exception as e:
            logger.error(f"Unexpected error publishing to MQTT: {e}")
            return False

    async def publish_dict(
        self,
        base_topic: str,
        data: dict[str, Any],
        force: bool = False,
    ) -> int:
        """Publish each key-value pair as a separate topic.

        Args:
            base_topic: Base topic for all values.
            data: Dictionary of values to publish.
            force: Force publish even if values haven't changed.

        Returns:
            Number of successfully published messages.
        """
        published = 0

        for key, value in data.items():
            # Skip None values and internal keys
            if value is None or key.startswith("_"):
                continue

            topic = f"{base_topic}/{key}"

            if await self.publish(topic, value, force=force):
                published += 1

        return published

    def _has_value_changed(self, topic: str, new_value: Any) -> bool:
        """Check if a value has changed since last publish.

        Args:
            topic: Full topic path.
            new_value: New value to compare.

        Returns:
            True if value changed or is new, False if unchanged.
        """
        if topic not in self._last_values:
            return True

        old_value = self._last_values[topic]

        # Handle floating point comparison with tolerance
        if isinstance(new_value, float) and isinstance(old_value, float):
            return abs(new_value - old_value) > 0.001

        # Handle dict comparison
        if isinstance(new_value, dict) and isinstance(old_value, dict):
            return new_value != old_value

        return new_value != old_value

    def clear_cache(self) -> None:
        """Clear the value cache, forcing next publish to send all values."""
        self._last_values.clear()
        logger.debug("MQTT value cache cleared")
