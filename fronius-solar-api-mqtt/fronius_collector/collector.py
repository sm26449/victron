"""Fronius data collector using pyfronius library."""

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

import aiohttp

# Add parent directory to path to import pyfronius
sys.path.insert(0, str(Path(__file__).parent.parent))

from pyfronius import Fronius

from .config import FroniusConfig
from .const import (
    get_error_description,
    get_status_description,
    get_status_name,
    is_status_alarm,
)
from .influxdb_client import InfluxClient
from .mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class FroniusCollector:
    """Collects data from Fronius devices and publishes to MQTT/InfluxDB."""

    def __init__(
        self,
        fronius_config: FroniusConfig,
        mqtt_client: Optional[MQTTClient] = None,
        influx_client: Optional[InfluxClient] = None,
    ):
        """Initialize the collector.

        Args:
            fronius_config: Fronius device configuration.
            mqtt_client: Optional MQTT client for publishing.
            influx_client: Optional InfluxDB client for storing.
        """
        self.config = fronius_config
        self.mqtt = mqtt_client
        self.influx = influx_client

        self._session: Optional[aiohttp.ClientSession] = None
        self._fronius: Optional[Fronius] = None
        self._running = False
        self._collect_task: Optional[asyncio.Task] = None
        self._collect_task_fast: Optional[asyncio.Task] = None
        self._collect_task_slow: Optional[asyncio.Task] = None
        # Cache for inverter info (updated less frequently)
        self._inverter_info_cache: Optional[dict] = None
        self._last_inverter_info_update: float = 0

    async def start(self) -> None:
        """Start the collector."""
        self._running = True

        # Create aiohttp session
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        self._session = aiohttp.ClientSession(timeout=timeout)

        # Create Fronius client
        self._fronius = Fronius(self._session, self.config.host)

        # Detect API version
        try:
            api_version = await self._fronius.fetch_api_version()
            logger.info(f"Connected to Fronius at {self.config.host}, API version: {api_version}")
        except Exception as e:
            logger.warning(f"Could not detect API version: {e}")

        # Start collection loops
        if self.config.poll_interval_fast > 0:
            # Fast polling mode: separate loops for fast and slow data
            self._collect_task_fast = asyncio.create_task(self._collection_loop_fast())
            self._collect_task_slow = asyncio.create_task(self._collection_loop_slow())
            logger.info(
                f"Fronius collector started (fast: {self.config.poll_interval_fast}s, "
                f"slow: {self.config.poll_interval}s, "
                f"info: {self.config.poll_interval_inverter_info}s)"
            )
        else:
            # Normal mode: single loop for all data
            self._collect_task = asyncio.create_task(self._collection_loop())
            logger.info(f"Fronius collector started (poll: {self.config.poll_interval}s)")

    async def stop(self) -> None:
        """Stop the collector."""
        self._running = False

        # Cancel all collection tasks
        for task in [self._collect_task, self._collect_task_fast, self._collect_task_slow]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self._session:
            await self._session.close()
            self._session = None

        self._fronius = None
        logger.info("Fronius collector stopped")

    async def _collection_loop(self) -> None:
        """Main collection loop (normal mode - all data at same interval)."""
        while self._running:
            try:
                await self._collect_and_publish()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in collection loop: {e}")

            # Wait for next poll
            await asyncio.sleep(self.config.poll_interval)

    async def _collection_loop_fast(self) -> None:
        """Fast collection loop for power_flow and meter data."""
        while self._running:
            try:
                await self._collect_fast_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in fast collection loop: {e}")

            await asyncio.sleep(self.config.poll_interval_fast)

    async def _collection_loop_slow(self) -> None:
        """Slow collection loop for inverter data and logger status."""
        while self._running:
            try:
                await self._collect_inverter_data()
                await self._collect_logger_status()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in slow collection loop: {e}")

            await asyncio.sleep(self.config.poll_interval)

    async def _collect_fast_data(self) -> None:
        """Collect fast-changing data (power flow and meter)."""
        if not self._fronius:
            return

        # Run power_flow and meter in parallel for speed
        await asyncio.gather(
            self._collect_power_flow(),
            self._collect_meter_data(),
            return_exceptions=True,
        )

    async def _collect_and_publish(self) -> None:
        """Collect data from Fronius and publish to outputs."""
        if not self._fronius:
            return

        # Collect power flow data
        await self._collect_power_flow()

        # Collect meter data
        await self._collect_meter_data()

        # Collect inverter data (system-wide + info)
        await self._collect_inverter_data()

        # Collect logger/datamanager status
        await self._collect_logger_status()

    async def _collect_power_flow(self) -> None:
        """Collect and publish power flow data."""
        try:
            data = await self._fronius.current_power_flow()
            if not data:
                logger.warning("No power flow data received")
                return

            logger.debug(f"Power flow: {data}")

            # Extract relevant fields
            fields = self._extract_power_flow_fields(data)

            # Publish to MQTT
            if self.mqtt:
                await self.mqtt.publish_dict("power_flow", fields)

            # Write to InfluxDB
            if self.influx:
                await self.influx.write_power_flow(fields)

        except Exception as e:
            logger.error(f"Error collecting power flow: {e}")

    async def _collect_meter_data(self) -> None:
        """Collect and publish meter data using system endpoint."""
        try:
            data = await self._fronius.current_system_meter_data()
            if not data or "meters" not in data:
                logger.warning("No meter data received")
                return

            # Process each meter in the system
            for meter_id, meter_data in data["meters"].items():
                logger.debug(f"Meter {meter_id}: {meter_data}")

                # Extract all fields from meter data
                fields = self._extract_meter_fields(meter_data)

                # Publish to MQTT
                if self.mqtt:
                    await self.mqtt.publish_dict(f"meter/{meter_id}", fields)

                # Write to InfluxDB
                if self.influx:
                    await self.influx.write_meter_data(int(meter_id), fields)

        except Exception as e:
            logger.error(f"Error collecting meter data: {e}")

    async def _collect_inverter_data(self) -> None:
        """Collect and publish inverter data using detailed per-device endpoints."""
        try:
            # Get inverter info (contains pv_power, custom_name, unique_id)
            # This is cached and updated less frequently
            now = time.time()
            if (
                self._inverter_info_cache is None
                or (now - self._last_inverter_info_update) >= self.config.poll_interval_inverter_info
            ):
                inv_info = await self._fronius.inverter_info()
                if inv_info:
                    self._inverter_info_cache = inv_info
                    self._last_inverter_info_update = now
                    logger.debug("Inverter info cache updated")
            else:
                inv_info = self._inverter_info_cache

            inv_info_map = {}
            if inv_info and "inverters" in inv_info:
                for inv in inv_info["inverters"]:
                    dev_id = self._get_value(inv.get("device_id"))
                    if dev_id:
                        inv_info_map[str(dev_id)] = inv

            # Calculate total PV power installed from inverter info
            pv_power_total = 0
            for inv in inv_info_map.values():
                pv = self._get_value(inv.get("pv_power"))
                if pv:
                    pv_power_total += pv

            # Collect detailed data for each inverter in parallel
            inverter_ids = [str(i) for i in self.config.inverter_ids]

            # Create tasks for all inverter data requests
            common_tasks = [
                self._fronius.current_inverter_data(inv_id)
                for inv_id in inverter_ids
            ]
            threep_tasks = [
                self._fronius.current_inverter_3p_data(inv_id)
                for inv_id in inverter_ids
            ]

            # Run all requests in parallel
            all_results = await asyncio.gather(
                *common_tasks, *threep_tasks,
                return_exceptions=True
            )

            # Split results
            common_results = all_results[:len(inverter_ids)]
            threep_results = all_results[len(inverter_ids):]

            # Calculate system totals
            total_power = 0
            total_energy_day = 0
            total_energy_year = 0
            total_energy_total = 0

            # Process each inverter
            for idx, inv_id in enumerate(inverter_ids):
                common_data = common_results[idx]
                threep_data = threep_results[idx]

                # Skip if we got an exception
                if isinstance(common_data, Exception):
                    logger.warning(f"Error getting inverter {inv_id} common data: {common_data}")
                    continue

                logger.debug(f"Inverter {inv_id} common: {common_data}")
                logger.debug(f"Inverter {inv_id} 3p: {threep_data}")

                # Extract all fields from common data
                fields = self._extract_inverter_fields(common_data)

                # Add 3-phase data if available
                if not isinstance(threep_data, Exception) and threep_data:
                    threep_fields = self._extract_inverter_3p_fields(threep_data)
                    fields.update(threep_fields)

                # Accumulate totals
                power = fields.get("power", 0) or 0
                total_power += power
                total_energy_day += fields.get("energy_day", 0) or 0
                total_energy_year += fields.get("energy_year", 0) or 0
                total_energy_total += fields.get("energy_total", 0) or 0

                # Add info fields (pv_power, custom_name, etc.)
                if inv_id in inv_info_map:
                    info = inv_info_map[inv_id]
                    status_code = self._get_value(info.get("status_code"))
                    error_code = self._get_value(info.get("error_code"))

                    info_fields = {
                        "pv_power": self._get_value(info.get("pv_power")),
                        "custom_name": self._get_value(info.get("custom_name")),
                        "unique_id": self._get_value(info.get("unique_id")),
                    }

                    # Update status/error from info (if not already in common data)
                    if status_code is not None and "status_code" not in fields:
                        fields["status_code"] = status_code
                    if error_code is not None and "error_code" not in fields:
                        fields["error_code"] = error_code

                    # Add human-readable status and error descriptions
                    sc = fields.get("status_code")
                    ec = fields.get("error_code")
                    if sc is not None:
                        info_fields["status"] = get_status_description(sc)
                        info_fields["status_name"] = get_status_name(sc)
                        info_fields["alarm"] = is_status_alarm(sc)
                    if ec is not None:
                        info_fields["error"] = get_error_description(ec)

                    # Add device type info if available
                    device_type = info.get("device_type", {})
                    if isinstance(device_type, dict):
                        if "manufacturer" in device_type:
                            info_fields["manufacturer"] = device_type.get("manufacturer")
                        if "model" in device_type:
                            info_fields["model"] = device_type.get("model")
                        info_fields["device_type"] = self._get_value(device_type)
                    else:
                        info_fields["device_type"] = self._get_value(device_type)

                    # Calculate efficiency per inverter
                    inv_pv_power = self._get_value(info.get("pv_power")) or 0
                    if inv_pv_power > 0 and power > 0:
                        info_fields["efficiency"] = round((power / inv_pv_power) * 100, 2)
                    else:
                        info_fields["efficiency"] = 0.0

                    # Merge info fields (don't overwrite existing)
                    for k, v in info_fields.items():
                        if v is not None and k not in fields:
                            fields[k] = v

                # Publish to MQTT
                if self.mqtt:
                    await self.mqtt.publish_dict(f"inverter/{inv_id}", fields)

                # Write to InfluxDB
                if self.influx:
                    await self.influx.write_inverter_data(int(inv_id), fields)

            # Publish system totals
            system_fields = {
                "power": total_power,
                "energy_day": total_energy_day,
                "energy_year": total_energy_year,
                "energy_total": total_energy_total,
                "pv_power_total": pv_power_total,
            }

            # Calculate efficiency (only when producing and pv_power_total > 0)
            if pv_power_total > 0 and total_power > 0:
                system_fields["efficiency"] = round((total_power / pv_power_total) * 100, 2)
            else:
                system_fields["efficiency"] = 0.0

            system_fields = {k: v for k, v in system_fields.items() if v is not None}

            if self.mqtt and system_fields:
                await self.mqtt.publish_dict("inverter/total", system_fields)

            if self.influx and system_fields:
                await self.influx.write("inverter_total", system_fields)

        except Exception as e:
            logger.error(f"Error collecting inverter data: {e}")

    async def _collect_logger_status(self) -> None:
        """Collect and publish DataManager/logger status."""
        try:
            # Get logger LED status
            led_data = await self._fronius.current_led_data()
            if led_data:
                fields = {}
                # Extract LED states (pyfronius uses snake_case names)
                led_mappings = {
                    "power_led": "power_led",
                    "solar_net_led": "solarnet_led",
                    "solar_web_led": "solarweb_led",
                    "wlan_led": "wlan_led",
                }
                for src_name, dst_name in led_mappings.items():
                    if src_name in led_data:
                        led_info = led_data[src_name]
                        # Convert to simple format: "green_on", "red_blinking", etc.
                        color = led_info.get("color", "unknown")
                        state = led_info.get("state", "unknown")
                        fields[dst_name] = f"{color}_{state}"

                # Add online status (if we got here, we're online)
                fields["online"] = True
                fields["last_update"] = int(time.time())

                if self.mqtt and fields:
                    await self.mqtt.publish_dict("logger", fields)

                if self.influx and fields:
                    await self.influx.write("logger", fields)

        except Exception as e:
            # If we can't reach the logger, mark as offline
            logger.error(f"Error collecting logger status: {e}")
            if self.mqtt:
                await self.mqtt.publish("logger/online", False)

    def _get_value(self, data: Any) -> Any:
        """Extract value from Fronius data format.

        Fronius returns data as {'value': X, 'unit': 'Y'} or just plain values.

        Args:
            data: Raw data from Fronius.

        Returns:
            Extracted value or None.
        """
        if data is None:
            return None
        if isinstance(data, dict):
            return data.get("value")
        return data

    def _extract_power_flow_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract relevant fields from power flow data.

        Args:
            data: Raw power flow data from Fronius.

        Returns:
            Dictionary of field names to values.
        """
        fields = {}

        # Map common power flow fields
        field_mappings = {
            "power_grid": "grid_power",
            "power_load": "load_power",
            "power_photovoltaics": "pv_power",
            "power_battery": "battery_power",
            "relative_autonomy": "autonomy",
            "relative_self_consumption": "self_consumption",
            "energy_day": "energy_day",
            "energy_year": "energy_year",
            "energy_total": "energy_total",
            "meter_location": "meter_location",
        }

        for src_key, dst_key in field_mappings.items():
            if src_key in data:
                value = self._get_value(data[src_key])
                if value is not None:
                    fields[dst_key] = value

        return fields

    def _extract_meter_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract all fields from meter data.

        Args:
            data: Raw meter data from Fronius.

        Returns:
            Dictionary of field names to values.
        """
        fields = {}

        # Map all meter fields to cleaner names
        field_mappings = {
            # Power
            "power_real": "power",
            "power_real_phase_1": "power_l1",
            "power_real_phase_2": "power_l2",
            "power_real_phase_3": "power_l3",
            "power_apparent": "apparent_power",
            "power_apparent_phase_1": "apparent_power_l1",
            "power_apparent_phase_2": "apparent_power_l2",
            "power_apparent_phase_3": "apparent_power_l3",
            "power_reactive": "reactive_power",
            "power_reactive_phase_1": "reactive_power_l1",
            "power_reactive_phase_2": "reactive_power_l2",
            "power_reactive_phase_3": "reactive_power_l3",
            # Current
            "current_ac_phase_1": "current_l1",
            "current_ac_phase_2": "current_l2",
            "current_ac_phase_3": "current_l3",
            # Voltage phase to neutral
            "voltage_ac_phase_1": "voltage_l1",
            "voltage_ac_phase_2": "voltage_l2",
            "voltage_ac_phase_3": "voltage_l3",
            # Voltage phase to phase
            "voltage_ac_phase_to_phase_12": "voltage_l1_l2",
            "voltage_ac_phase_to_phase_23": "voltage_l2_l3",
            "voltage_ac_phase_to_phase_31": "voltage_l3_l1",
            # Power factor
            "power_factor": "power_factor",
            "power_factor_phase_1": "power_factor_l1",
            "power_factor_phase_2": "power_factor_l2",
            "power_factor_phase_3": "power_factor_l3",
            # Frequency
            "frequency_phase_average": "frequency",
            # Energy
            "energy_real_consumed": "energy_consumed",
            "energy_real_produced": "energy_produced",
            "energy_real_ac_plus": "energy_import",
            "energy_real_ac_minus": "energy_export",
            "energy_reactive_ac_consumed": "reactive_energy_consumed",
            "energy_reactive_ac_produced": "reactive_energy_produced",
            # Meter info
            "meter_location": "location",
            "manufacturer": "manufacturer",
            "model": "model",
            "serial": "serial",
        }

        for src_key, dst_key in field_mappings.items():
            if src_key in data:
                value = self._get_value(data[src_key])
                if value is not None:
                    fields[dst_key] = value

        return fields

    def _extract_inverter_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract all fields from inverter common data.

        Args:
            data: Raw inverter data from Fronius.

        Returns:
            Dictionary of field names to values.
        """
        fields = {}

        # Map all inverter fields from CommonInverterData
        field_mappings = {
            # Power & Energy
            "power_ac": "power",
            "energy_day": "energy_day",
            "energy_year": "energy_year",
            "energy_total": "energy_total",
            # AC side
            "current_ac": "current_ac",
            "voltage_ac": "voltage_ac",
            "frequency_ac": "frequency",
            # DC side (MPPT 1)
            "current_dc": "dc_current",
            "voltage_dc": "dc_voltage",
            # DC side (MPPT 2+)
            "current_dc_2": "dc_current_2",
            "voltage_dc_2": "dc_voltage_2",
            "current_dc_3": "dc_current_3",
            "voltage_dc_3": "dc_voltage_3",
            # Status
            "status_code": "status_code",
            "error_code": "error_code",
            "inverter_state": "inverter_state",
            "led_state": "led_state",
            "led_color": "led_color",
        }

        for src_key, dst_key in field_mappings.items():
            if src_key in data:
                value = self._get_value(data[src_key])
                if value is not None:
                    fields[dst_key] = value

        # Calculate DC power if we have voltage and current
        dc_voltage = fields.get("dc_voltage", 0) or 0
        dc_current = fields.get("dc_current", 0) or 0
        if dc_voltage > 0 and dc_current > 0:
            fields["dc_power"] = round(dc_voltage * dc_current, 1)

        return fields

    def _extract_inverter_3p_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract all fields from inverter 3-phase data.

        Args:
            data: Raw inverter 3P data from Fronius.

        Returns:
            Dictionary of field names to values.
        """
        fields = {}

        # Map 3-phase inverter fields
        field_mappings = {
            "current_ac_phase_1": "current_l1",
            "current_ac_phase_2": "current_l2",
            "current_ac_phase_3": "current_l3",
            "voltage_ac_phase_1": "voltage_l1",
            "voltage_ac_phase_2": "voltage_l2",
            "voltage_ac_phase_3": "voltage_l3",
        }

        for src_key, dst_key in field_mappings.items():
            if src_key in data:
                value = self._get_value(data[src_key])
                if value is not None:
                    fields[dst_key] = value

        return fields

    async def collect_once(self) -> dict[str, Any]:
        """Collect all data once and return it.

        Useful for testing or manual data collection.

        Returns:
            Dictionary with all collected data.
        """
        if not self._fronius:
            raise RuntimeError("Collector not started")

        result = {
            "power_flow": None,
            "meter": {},
            "inverters": {},
        }

        try:
            result["power_flow"] = await self._fronius.current_power_flow()
        except Exception as e:
            logger.error(f"Error collecting power flow: {e}")

        try:
            result["meter"][self.config.meter_id] = await self._fronius.current_meter_data(
                self.config.meter_id
            )
        except Exception as e:
            logger.error(f"Error collecting meter data: {e}")

        for inverter_id in self.config.inverter_ids:
            try:
                result["inverters"][inverter_id] = await self._fronius.current_inverter_data(
                    inverter_id
                )
            except Exception as e:
                logger.error(f"Error collecting inverter {inverter_id}: {e}")

        return result
