"""Resilient InfluxDB v2 client for Fronius Collector."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.exceptions import InfluxDBError
from influxdb_client.client.write_api import ASYNCHRONOUS

from .config import InfluxDBConfig

logger = logging.getLogger(__name__)


class InfluxClient:
    """InfluxDB v2 client with automatic reconnection and change detection."""

    def __init__(self, config: InfluxDBConfig):
        """Initialize InfluxDB client.

        Args:
            config: InfluxDB configuration.
        """
        self.config = config
        self._client: Optional[InfluxDBClient] = None
        self._write_api = None
        self._connected = False
        self._last_values: dict[str, Any] = {}
        self._buffer: list[Point] = []
        self._last_flush = datetime.now(timezone.utc)
        self._reconnect_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        """Return True if connected to InfluxDB."""
        return self._connected

    async def start(self) -> None:
        """Start the InfluxDB client and connect."""
        if not self.config.enabled:
            logger.info("InfluxDB is disabled in config")
            return

        self._running = True
        await self._connect()

    async def stop(self) -> None:
        """Stop the InfluxDB client and flush remaining data."""
        self._running = False

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        # Flush remaining buffer
        await self._flush_buffer()
        await self._disconnect()
        logger.info("InfluxDB client stopped")

    async def _connect(self) -> None:
        """Connect to InfluxDB."""
        if not self._running:
            return

        try:
            self._client = InfluxDBClient(
                url=self.config.url,
                token=self.config.token,
                org=self.config.org,
            )

            # Test connection
            health = self._client.health()
            if health.status == "pass":
                self._write_api = self._client.write_api(write_options=ASYNCHRONOUS)
                self._connected = True
                logger.info(f"Connected to InfluxDB at {self.config.url}")
            else:
                raise ConnectionError(f"InfluxDB health check failed: {health.message}")

        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")
            self._connected = False
            self._schedule_reconnect()

    async def _disconnect(self) -> None:
        """Disconnect from InfluxDB."""
        if self._write_api:
            try:
                self._write_api.close()
            except Exception as e:
                logger.debug(f"Error closing write API: {e}")
            self._write_api = None

        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.debug(f"Error closing InfluxDB client: {e}")
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
        """Attempt to reconnect to InfluxDB."""
        reconnect_delay = 5  # Fixed delay for InfluxDB

        while self._running and not self._connected:
            logger.info(f"Attempting InfluxDB reconnection in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)

            if not self._running:
                break

            await self._disconnect()
            await self._connect()

    async def write(
        self,
        measurement: str,
        fields: dict[str, Any],
        tags: Optional[dict[str, str]] = None,
        timestamp: Optional[datetime] = None,
        force: bool = False,
    ) -> bool:
        """Write a data point to InfluxDB.

        Args:
            measurement: Measurement name.
            fields: Field values to write.
            tags: Optional tags for the point.
            timestamp: Optional timestamp (defaults to now).
            force: Force write even if values haven't changed.

        Returns:
            True if written successfully, False otherwise.
        """
        if not self.config.enabled:
            return False

        if not self._connected:
            logger.warning(f"Cannot write {measurement}: not connected")
            self._schedule_reconnect()
            return False

        # Filter out None values and check for changes
        filtered_fields = {}
        for key, value in fields.items():
            if value is None or key.startswith("_"):
                continue

            cache_key = f"{measurement}:{tags}:{key}" if tags else f"{measurement}:{key}"

            # Check for changes if in on_change mode
            if self.config.write_mode == "on_change" and not force:
                if not self._has_value_changed(cache_key, value):
                    continue

            filtered_fields[key] = value
            self._last_values[cache_key] = value

        if not filtered_fields:
            logger.debug(f"No changed fields for {measurement}")
            return True

        # Create point
        point = Point(measurement)

        if tags:
            for key, value in tags.items():
                point = point.tag(key, value)

        for key, value in filtered_fields.items():
            point = point.field(key, value)

        if timestamp:
            point = point.time(timestamp)

        # Add to buffer
        async with self._lock:
            self._buffer.append(point)

        # Check if we should flush
        buffer_full = len(self._buffer) >= self.config.batch_size
        time_elapsed = (
            datetime.now(timezone.utc) - self._last_flush
        ).total_seconds() >= self.config.flush_interval

        if buffer_full or time_elapsed:
            await self._flush_buffer()

        return True

    async def _flush_buffer(self) -> bool:
        """Flush buffered points to InfluxDB.

        Returns:
            True if flush was successful, False otherwise.
        """
        async with self._lock:
            if not self._buffer:
                return True

            if not self._connected or not self._write_api:
                logger.warning("Cannot flush: not connected to InfluxDB")
                return False

            points_to_write = self._buffer.copy()
            self._buffer.clear()

        try:
            # Run synchronous write in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._write_api.write,
                self.config.bucket,
                self.config.org,
                points_to_write,
            )

            self._last_flush = datetime.now(timezone.utc)
            logger.debug(f"Flushed {len(points_to_write)} points to InfluxDB")
            return True

        except InfluxDBError as e:
            logger.error(f"InfluxDB write error: {e}")
            # Put points back in buffer for retry
            async with self._lock:
                self._buffer = points_to_write + self._buffer
            self._connected = False
            self._schedule_reconnect()
            return False

        except Exception as e:
            logger.error(f"Unexpected error writing to InfluxDB: {e}")
            return False

    async def write_inverter_data(
        self,
        inverter_id: int,
        data: dict[str, Any],
        force: bool = False,
    ) -> bool:
        """Write inverter data to InfluxDB.

        Args:
            inverter_id: Inverter device ID.
            data: Inverter data dictionary.
            force: Force write even if values haven't changed.

        Returns:
            True if written successfully.
        """
        tags = {"inverter_id": str(inverter_id)}
        return await self.write(
            measurement="inverter",
            fields=data,
            tags=tags,
            force=force,
        )

    async def write_meter_data(
        self,
        meter_id: int,
        data: dict[str, Any],
        force: bool = False,
    ) -> bool:
        """Write meter data to InfluxDB.

        Args:
            meter_id: Meter device ID.
            data: Meter data dictionary.
            force: Force write even if values haven't changed.

        Returns:
            True if written successfully.
        """
        tags = {"meter_id": str(meter_id)}
        return await self.write(
            measurement="meter",
            fields=data,
            tags=tags,
            force=force,
        )

    async def write_power_flow(
        self,
        data: dict[str, Any],
        force: bool = False,
    ) -> bool:
        """Write power flow data to InfluxDB.

        Args:
            data: Power flow data dictionary.
            force: Force write even if values haven't changed.

        Returns:
            True if written successfully.
        """
        return await self.write(
            measurement="power_flow",
            fields=data,
            force=force,
        )

    def _has_value_changed(self, key: str, new_value: Any) -> bool:
        """Check if a value has changed since last write.

        Args:
            key: Cache key.
            new_value: New value to compare.

        Returns:
            True if value changed or is new, False if unchanged.
        """
        if key not in self._last_values:
            return True

        old_value = self._last_values[key]

        # Handle floating point comparison with tolerance
        if isinstance(new_value, float) and isinstance(old_value, float):
            return abs(new_value - old_value) > 0.001

        return new_value != old_value

    def clear_cache(self) -> None:
        """Clear the value cache, forcing next write to send all values."""
        self._last_values.clear()
        logger.debug("InfluxDB value cache cleared")

    async def force_flush(self) -> bool:
        """Force an immediate flush of the buffer.

        Returns:
            True if flush was successful.
        """
        return await self._flush_buffer()
