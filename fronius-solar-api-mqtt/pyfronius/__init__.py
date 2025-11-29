"""
Fronius Solar API Client Library.

Created on 27.09.2017
@author: Niels
@author: Gerrit Beine
@author: Refactored 2024
"""

import asyncio
import enum
import logging
from typing import Any, Callable, Dict, Final, Iterable, List, Optional, Tuple, Union

import aiohttp

from .const import INVERTER_DEVICE_TYPE, OHMPILOT_STATE_CODES
from .units import (
    AMPERE, DEGREE_CELSIUS, HERTZ, PERCENT, VOLT, VOLTAMPERE,
    VOLTAMPEREREACTIVE, VOLTAMPEREREACTIVE_HOUR, WATT, WATT_HOUR
)
from .parsers import (
    parse_led_data,
    parse_power_flow,
    parse_meter_data,
    parse_system_meter_data,
    parse_inverter_data,
    parse_inverter_3p_data,
    parse_system_inverter_data,
    parse_storage_data,
    parse_system_storage_data,
    parse_ohmpilot_data,
    parse_system_ohmpilot_data,
    parse_active_device_info,
    parse_inverter_info,
    parse_logger_info,
)

_LOGGER = logging.getLogger(__name__)

# Re-export for backwards compatibility
__all__ = [
    "Fronius",
    "FroniusError",
    "NotSupportedError",
    "FroniusConnectionError",
    "InvalidAnswerError",
    "BadStatusError",
    "API_VERSION",
    "INVERTER_DEVICE_TYPE",
    "OHMPILOT_STATE_CODES",
    # Units
    "DEGREE_CELSIUS",
    "WATT",
    "WATT_HOUR",
    "AMPERE",
    "VOLT",
    "PERCENT",
    "HERTZ",
    "VOLTAMPEREREACTIVE",
    "VOLTAMPEREREACTIVE_HOUR",
    "VOLTAMPERE",
]


class API_VERSION(enum.Enum):
    """Fronius Solar API version."""
    value: int

    AUTO = -1
    V0 = 0
    V1 = 1


API_BASEPATHS: Final = {
    API_VERSION.V0: "/solar_api/",
    API_VERSION.V1: "/solar_api/v1/",
}

# API endpoints
URL_API_VERSION: Final = "solar_api/GetAPIVersion.cgi"
URL_POWER_FLOW: Final = {API_VERSION.V1: "GetPowerFlowRealtimeData.fcgi"}
URL_SYSTEM_METER: Final = {API_VERSION.V1: "GetMeterRealtimeData.cgi?Scope=System"}
URL_SYSTEM_INVERTER: Final = {
    API_VERSION.V0: "GetInverterRealtimeData.cgi?Scope=System",
    API_VERSION.V1: "GetInverterRealtimeData.cgi?Scope=System",
}
URL_SYSTEM_LED: Final = {API_VERSION.V1: "GetLoggerLEDInfo.cgi"}
URL_SYSTEM_OHMPILOT: Final = {
    API_VERSION.V1: "GetOhmPilotRealtimeData.cgi?Scope=System"
}
URL_SYSTEM_STORAGE: Final = {
    API_VERSION.V1: "GetStorageRealtimeData.cgi?Scope=System"
}
URL_DEVICE_METER: Final = {
    API_VERSION.V1: "GetMeterRealtimeData.cgi?Scope=Device&DeviceId={}"
}
URL_DEVICE_STORAGE: Final = {
    API_VERSION.V1: "GetStorageRealtimeData.cgi?Scope=Device&DeviceId={}"
}
URL_DEVICE_INVERTER_CUMULATIVE: Final = {
    API_VERSION.V0: (
        "GetInverterRealtimeData.cgi?Scope=Device&"
        "DeviceIndex={}&"
        "DataCollection=CumulationInverterData"
    ),
    API_VERSION.V1: (
        "GetInverterRealtimeData.cgi?Scope=Device&"
        "DeviceId={}&"
        "DataCollection=CumulationInverterData"
    ),
}
URL_DEVICE_INVERTER_COMMON: Final = {
    API_VERSION.V0: (
        "GetInverterRealtimeData.cgi?Scope=Device&"
        "DeviceIndex={}&"
        "DataCollection=CommonInverterData"
    ),
    API_VERSION.V1: (
        "GetInverterRealtimeData.cgi?Scope=Device&"
        "DeviceId={}&"
        "DataCollection=CommonInverterData"
    ),
}
URL_DEVICE_INVERTER_3P: Final = {
    API_VERSION.V1: (
        "GetInverterRealtimeData.cgi?Scope=Device&"
        "DeviceId={}&"
        "DataCollection=3PInverterData"
    ),
}
URL_ACTIVE_DEVICE_INFO_SYSTEM: Final = {
    API_VERSION.V1: "GetActiveDeviceInfo.cgi?DeviceClass=System"
}
URL_INVERTER_INFO: Final = {
    API_VERSION.V0: "GetInverterInfo.cgi",
    API_VERSION.V1: "GetInverterInfo.cgi",
}
URL_LOGGER_INFO: Final = {
    API_VERSION.V0: "GetLoggerInfo.cgi",
    API_VERSION.V1: "GetLoggerInfo.cgi",
}

HEADER_STATUS_CODES: Final = {
    0: "OKAY",
    1: "NotImplemented",
    2: "Uninitialized",
    3: "Initialized",
    4: "Running",
    5: "Timeout",
    6: "Argument Error",
    7: "LNRequestError",
    8: "LNRequestTimeout",
    9: "LNParseError",
    10: "ConfigIOError",
    11: "NotSupported",
    12: "DeviceNotAvailable",
    255: "UnknownError",
}


# =============================================================================
# Exceptions
# =============================================================================

class FroniusError(Exception):
    """Base exception for Fronius errors."""


class NotSupportedError(ValueError, FroniusError):
    """Feature not supported by device."""


class FroniusConnectionError(ConnectionError, FroniusError):
    """Connection to Fronius device failed."""


class InvalidAnswerError(ValueError, FroniusError):
    """Invalid response from Fronius device."""


class BadStatusError(FroniusError):
    """Bad status code returned from API."""

    def __init__(
        self,
        endpoint: str,
        code: int,
        reason: Optional[str] = None,
        response: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize exception."""
        self.response = response or {}
        message = (
            f"BadStatusError at {endpoint}. "
            f"Code: {code} - {HEADER_STATUS_CODES.get(code, 'unknown status code')}. "
            f"Reason: {reason or 'unknown'}."
        )
        super().__init__(message)


# =============================================================================
# Main Fronius Client
# =============================================================================

class Fronius:
    """
    Async client for Fronius Solar API.

    Communicates with Fronius inverters via HTTP/JSON API.

    Attributes:
        session: aiohttp ClientSession for HTTP requests
        url: Base URL of the Fronius device (e.g., http://192.168.0.10)
        api_version: API version to use (AUTO for automatic detection)
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        api_version: API_VERSION = API_VERSION.AUTO,
    ) -> None:
        """
        Initialize Fronius client.

        Args:
            session: aiohttp ClientSession
            url: Fronius device URL
            api_version: API version (default: AUTO)
        """
        self._aio_session = session
        # Remove trailing slashes
        while url.endswith("/"):
            url = url[:-1]
        self.url = url
        # Prepend http:// if missing
        if not self.url.startswith("http"):
            self.url = f"http://{self.url}"
        self.api_version = api_version
        self.base_url = API_BASEPATHS.get(api_version)

    async def _fetch_json(self, url: str) -> Dict[str, Any]:
        """Fetch JSON from URL."""
        try:
            async with self._aio_session.get(url) as res:
                return await res.json(content_type=None)
        except asyncio.TimeoutError:
            raise FroniusConnectionError(
                f"Connection to Fronius device timed out at {url}."
            )
        except aiohttp.ClientError:
            raise FroniusConnectionError(
                f"Connection to Fronius device failed at {url}."
            )
        except (aiohttp.ContentTypeError, ValueError):
            raise InvalidAnswerError(
                f"Host returned a non-JSON reply at {url}."
            )

    async def fetch_api_version(self) -> Tuple[API_VERSION, str]:
        """
        Fetch the highest supported API version.

        Returns:
            Tuple of (API_VERSION, base_url)
        """
        try:
            res = await self._fetch_json(f"{self.url}/{URL_API_VERSION}")
            return API_VERSION(res["APIVersion"]), res["BaseURL"]
        except InvalidAnswerError:
            # Host returns 404 if API version is 0
            return API_VERSION.V0, API_BASEPATHS[API_VERSION.V0]

    async def _fetch_solar_api(
        self,
        spec: Dict[API_VERSION, str],
        spec_name: str,
        *spec_formattings: str,
    ) -> Dict[str, Any]:
        """Fetch from solar_api endpoint."""
        # Auto-detect API version if needed
        if self.base_url is None:
            prev_api_version = self.api_version
            self.api_version, self.base_url = await self.fetch_api_version()
            if prev_api_version == API_VERSION.AUTO:
                _LOGGER.debug(
                    "Using highest supported API version %s", self.api_version
                )
            elif prev_api_version != self.api_version:
                _LOGGER.warning(
                    "Unknown API version %s not supported by host %s, "
                    "using %s instead",
                    prev_api_version, self.url, self.api_version
                )

        spec_url = spec.get(self.api_version)
        if spec_url is None:
            raise NotSupportedError(
                f"API version {self.api_version} does not support {spec_name}"
            )

        if spec_formattings:
            spec_url = spec_url.format(*spec_formattings)

        _LOGGER.debug("Get %s data for %s", spec_name, spec_url)
        return await self._fetch_json(f"{self.url}{self.base_url}{spec_url}")

    @staticmethod
    def _status_data(res: Dict[str, Any]) -> Dict[str, Any]:
        """Extract status data from response."""
        return {
            "timestamp": {"value": res["Head"]["Timestamp"]},
            "status": res["Head"]["Status"],
        }

    @staticmethod
    def error_code(sensor_data: Dict[str, Any]) -> Any:
        """Extract error code from sensor data."""
        return sensor_data["status"]["Code"]

    @staticmethod
    def error_reason(sensor_data: Dict[str, Any]) -> Any:
        """Extract error reason from sensor data."""
        return sensor_data["status"]["Reason"]

    async def _current_data(
        self,
        parser: Callable[[Dict[str, Any]], Dict[str, Any]],
        spec: Dict[API_VERSION, str],
        spec_name: str,
        *spec_formattings: str,
    ) -> Dict[str, Any]:
        """Fetch and parse current data."""
        try:
            res = await self._fetch_solar_api(spec, spec_name, *spec_formattings)
        except InvalidAnswerError:
            raise NotSupportedError(
                f"Device type {spec_name} not supported by the Fronius device"
            )

        sensor: Dict[str, Any] = {}

        # Parse header/status
        try:
            sensor.update(Fronius._status_data(res))
        except (TypeError, KeyError):
            raise InvalidAnswerError(
                f"No header data returned from {spec} ({spec_formattings})"
            )

        # Check status code
        if sensor["status"]["Code"] != 0:
            endpoint = spec[self.api_version]
            code = sensor["status"]["Code"]
            reason = sensor["status"]["Reason"]
            raise BadStatusError(endpoint, code, reason=reason, response=sensor)

        # Parse body data
        try:
            sensor.update(parser(res["Body"]["Data"]))
        except (TypeError, KeyError):
            # LoggerInfo uses different structure
            try:
                sensor.update(parser(res["Body"]["LoggerInfo"]))
            except (TypeError, KeyError):
                raise InvalidAnswerError(
                    f"No body data returned from {spec} ({spec_formattings})"
                )

        return sensor

    # =========================================================================
    # Public API Methods
    # =========================================================================

    async def fetch(
        self,
        active_device_info: bool = True,
        inverter_info: bool = True,
        logger_info: bool = True,
        power_flow: bool = True,
        system_meter: bool = True,
        system_inverter: bool = True,
        system_ohmpilot: bool = True,
        system_storage: bool = True,
        device_meter: Iterable[str] = frozenset(["0"]),
        device_storage: Iterable[str] = frozenset(["0"]),
        device_inverter: Iterable[str] = frozenset(["1"]),
    ) -> List[Dict[str, Any]]:
        """
        Fetch all requested data in parallel.

        Args:
            active_device_info: Fetch active device info
            inverter_info: Fetch inverter info
            logger_info: Fetch logger info
            power_flow: Fetch power flow data
            system_meter: Fetch system meter data
            system_inverter: Fetch system inverter data
            system_ohmpilot: Fetch system ohmpilot data
            system_storage: Fetch system storage data
            device_meter: Device IDs for meter data
            device_storage: Device IDs for storage data
            device_inverter: Device IDs for inverter data

        Returns:
            List of response dictionaries
        """
        requests = []

        if active_device_info:
            requests.append(self.current_active_device_info())
        if inverter_info:
            requests.append(self.inverter_info())
        if logger_info:
            requests.append(self.current_logger_info())
        if power_flow:
            requests.append(self.current_power_flow())
        if system_meter:
            requests.append(self.current_system_meter_data())
        if system_inverter:
            requests.append(self.current_system_inverter_data())
        if system_ohmpilot:
            requests.append(self.current_system_ohmpilot_data())
        if system_storage:
            requests.append(self.current_system_storage_data())

        for i in device_meter:
            requests.append(self.current_meter_data(i))
        for i in device_storage:
            requests.append(self.current_storage_data(i))
        for i in device_inverter:
            requests.append(self.current_inverter_data(i))
        for i in device_inverter:
            requests.append(self.current_inverter_3p_data(i))

        results = await asyncio.gather(*requests, return_exceptions=True)

        responses = []
        for result in results:
            if isinstance(result, (FroniusError, BaseException)):
                _LOGGER.warning(result)
                if isinstance(result, BadStatusError):
                    responses.append(result.response)
                continue
            responses.append(result)

        return responses

    async def current_power_flow(
        self,
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current power flow data."""
        parser = ext_cb_conversion or parse_power_flow
        return await self._current_data(parser, URL_POWER_FLOW, "current power flow")

    async def current_system_meter_data(
        self,
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current system meter data."""
        parser = ext_cb_conversion or parse_system_meter_data
        return await self._current_data(parser, URL_SYSTEM_METER, "current system meter")

    async def current_system_inverter_data(
        self,
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current system inverter data."""
        parser = ext_cb_conversion or parse_system_inverter_data
        return await self._current_data(
            parser, URL_SYSTEM_INVERTER, "current system inverter"
        )

    async def current_system_ohmpilot_data(
        self,
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current system OhmPilot data."""
        parser = ext_cb_conversion or parse_system_ohmpilot_data
        return await self._current_data(
            parser, URL_SYSTEM_OHMPILOT, "current system ohmpilot"
        )

    async def current_meter_data(
        self,
        device: str = "0",
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current meter data for a device."""
        parser = ext_cb_conversion or parse_meter_data
        return await self._current_data(
            parser, URL_DEVICE_METER, "current meter", device
        )

    async def current_storage_data(
        self,
        device: str = "0",
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current storage data for a device."""
        parser = ext_cb_conversion or parse_storage_data
        return await self._current_data(
            parser, URL_DEVICE_STORAGE, "current storage", device
        )

    async def current_system_storage_data(
        self,
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current system storage data."""
        parser = ext_cb_conversion or parse_system_storage_data
        return await self._current_data(
            parser, URL_SYSTEM_STORAGE, "current system storage"
        )

    async def current_inverter_data(
        self,
        device: str = "1",
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current inverter data for a device."""
        parser = ext_cb_conversion or parse_inverter_data
        return await self._current_data(
            parser, URL_DEVICE_INVERTER_COMMON, "current inverter", device
        )

    async def current_inverter_3p_data(
        self,
        device: str = "1",
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current inverter 3-phase data for a device."""
        parser = ext_cb_conversion or parse_inverter_3p_data
        return await self._current_data(
            parser, URL_DEVICE_INVERTER_3P, "current inverter 3p", device
        )

    async def current_led_data(
        self,
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current LED status data."""
        parser = ext_cb_conversion or parse_led_data
        return await self._current_data(parser, URL_SYSTEM_LED, "current led")

    async def current_active_device_info(
        self,
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current active device info."""
        parser = ext_cb_conversion or parse_active_device_info
        return await self._current_data(
            parser, URL_ACTIVE_DEVICE_INFO_SYSTEM, "current active device info"
        )

    async def current_logger_info(
        self,
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get current logger info."""
        parser = ext_cb_conversion or parse_logger_info
        return await self._current_data(
            parser, URL_LOGGER_INFO, "current logger info"
        )

    async def inverter_info(
        self,
        ext_cb_conversion: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Get inverter info."""
        parser = ext_cb_conversion or parse_inverter_info
        return await self._current_data(parser, URL_INVERTER_INFO, "inverter info")

    # =========================================================================
    # Legacy static methods (kept for backwards compatibility)
    # =========================================================================

    @staticmethod
    def _system_led_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse LED data (legacy wrapper)."""
        return parse_led_data(data)

    @staticmethod
    def _system_power_flow(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse power flow data (legacy wrapper)."""
        return parse_power_flow(data)

    @staticmethod
    def _system_meter_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse system meter data (legacy wrapper)."""
        return parse_system_meter_data(data)

    @staticmethod
    def _device_meter_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse device meter data (legacy wrapper)."""
        return parse_meter_data(data)

    @staticmethod
    def _system_inverter_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse system inverter data (legacy wrapper)."""
        return parse_system_inverter_data(data)

    @staticmethod
    def _device_inverter_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse device inverter data (legacy wrapper)."""
        return parse_inverter_data(data)

    @staticmethod
    def _device_inverter_3p_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse device inverter 3p data (legacy wrapper)."""
        return parse_inverter_3p_data(data)

    @staticmethod
    def _device_storage_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse device storage data (legacy wrapper)."""
        return parse_storage_data(data)

    @staticmethod
    def _system_storage_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse system storage data (legacy wrapper)."""
        return parse_system_storage_data(data)

    @staticmethod
    def _device_ohmpilot_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse OhmPilot data (legacy wrapper)."""
        return parse_ohmpilot_data(data)

    @staticmethod
    def _system_ohmpilot_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse system OhmPilot data (legacy wrapper)."""
        return parse_system_ohmpilot_data(data)

    @staticmethod
    def _system_active_device_info(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse active device info (legacy wrapper)."""
        return parse_active_device_info(data)

    @staticmethod
    def _inverter_info(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse inverter info (legacy wrapper)."""
        return parse_inverter_info(data)

    @staticmethod
    def _logger_info(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse logger info (legacy wrapper)."""
        return parse_logger_info(data)

    @staticmethod
    def _controller_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse controller data (legacy wrapper)."""
        from .parsers import parse_controller_data
        return parse_controller_data(data)

    @staticmethod
    def _module_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse module data (legacy wrapper)."""
        from .parsers import parse_module_data
        return parse_module_data(data)
